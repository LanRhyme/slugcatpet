"""单实例锁：文件锁 + 本地 socket；后启实例通知主实例后自退，崩溃陈旧锁自动回收。"""
from __future__ import annotations
from PySide6.QtCore import QObject, QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .._paths import user_dir

_LOCK_NAME = "slugcatpet.lock"
_SERVER_KEY = "slugcatpet-single-instance"
_STALE_MS = 30_000          # 陈旧锁回收阈值


class SingleInstance(QObject):
    """主实例持锁+监听；后启实例连主实例通知后自退。"""

    def __init__(self, key: str = _SERVER_KEY, lock_path=None, parent=None):
        super().__init__(parent)
        self._key = key
        self._lock_path = str(lock_path or (user_dir() / _LOCK_NAME))
        self._lock = QLockFile(self._lock_path)
        self._lock.setStaleLockTime(_STALE_MS)
        self._server: QLocalServer | None = None
        self.on_secondary_attempt = None    # 主实例回调

    def acquire(self) -> bool:
        """尝试成为主实例，返回是否成功。"""
        if not self._try_lock():
            return False
        self._server = QLocalServer(self)
        QLocalServer.removeServer(self._key)          # 清崩溃残留 server
        if self._server.listen(self._key):
            self._server.newConnection.connect(self._on_new_connection)
        else:
            self._server = None                       # 监听失败仍算主
        return True

    def _try_lock(self) -> bool:
        ok = self._lock.tryLock(100)
        if not ok and self._lock.error() == QLockFile.LockError.LockFailedError:
            if self._lock.removeStaleLockFile():      # 回收陈旧锁重试
                ok = self._lock.tryLock(100)
        return ok

    def notify_primary(self, timeout_ms: int = 1000) -> bool:
        """通知主实例，返回是否成功。"""
        sock = QLocalSocket()
        sock.connectToServer(self._key)
        if not sock.waitForConnected(timeout_ms):
            return False
        sock.write(b"1")
        sock.flush()
        sock.waitForBytesWritten(timeout_ms)
        sock.disconnectFromServer()
        if sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
            sock.waitForDisconnected(timeout_ms)
        return True

    def _on_new_connection(self):
        """处理后启实例连接。"""
        if self._server is not None:
            sock = self._server.nextPendingConnection()
            if sock is not None:
                # lambda 排空，避免直连触发 PySide 告警
                sock.readyRead.connect(lambda s=sock: s.readAll())
                sock.disconnected.connect(sock.deleteLater)
        if callable(self.on_secondary_attempt):
            try:
                self.on_secondary_attempt()
            except Exception:
                pass

    def release(self):
        """关闭 server 并解锁。"""
        if self._server is not None:
            self._server.close()
            self._server = None
        self._lock.unlock()
