import struct
import ibapi
from ibapi.client import EClient
from ibapi.wrapper import EWrapper, iswrapper
import PyQt5.Qt as qt
import PyQt5.QtNetwork as qtnetwork

qApp = qt.QApplication([])


class TWSClient(EWrapper, EClient):
    """
    Version of ibapi.client.EClient that integrates with the Qt event loop.
    """
    def __init__(self):
        EClient.__init__(self, self)

    def reset(self):
        EClient.reset(self)
        self._data = b''

    def run(self):
        pass  # nothing needed, everything happens in _onSocketReadyRead

    def connect(self, host, port, clientId):
        self.host = host
        self.port = port
        self.clientId = clientId
        self.conn = TWSConnection(host, port)
        self.conn.connect()
        self.conn.socket.connected.connect(self._onSocketConnected)
        self.conn.socket.disconnected.connect(self._onSocketDisonnected)
        self.conn.socket.readyRead.connect(self._onSocketReadyRead)
        self.conn.socket.error.connect(self._onSocketError)
        self.setConnState(EClient.CONNECTING)

    def _prefix(self, msg):
        # prefix a message with its length
        return struct.pack('>I', len(msg)) + msg

    def _onSocketConnected(self):
        # start handshake
        msg = b'API\0'
        msg += self._prefix(b'v%d..%d' % (
                ibapi.server_versions.MIN_CLIENT_VER,
                ibapi.server_versions.MAX_CLIENT_VER))
        self.conn.sendMsg(msg)
        self.decoder = ibapi.decoder.Decoder(self.wrapper, None)

    def _onSocketDisonnected(self):
        EClient.disconnect(self)

    def _onSocketError(self, socketError):
        if self.conn.socket:
            print(self.conn.socket.errorString())

    def _onSocketReadyRead(self):
        self._data += bytes(self.conn.socket.readAll())

        while True:
            if len(self._data) <= 4:
                break
            # 4 byte prefix tells the message length
            msgEnd = 4 + struct.unpack('>I', self._data[:4])[0]
            if len(self._data) < msgEnd:
                # insufficient data for now
                break
            msg = self._data[4:msgEnd]
            self._data = self._data[msgEnd:]
            fields = msg.split(b'\0')
            fields.pop()  # pop off last empty element

            if not self.serverVersion_ and len(fields) == 2:
                # this concludes the handshake
                version, self.connTime = fields
                self.serverVersion_ = int(version)
                self.decoder.serverVersion = self.serverVersion_
                self.setConnState(EClient.CONNECTED)
                self.startApi()
                self.wrapper.connectAck()
            else:
                # decode and handle the message
                self.decoder.interpret(fields)


class TWSConnection:
    """
    This is a replacement for ibapi.connection.Connection that uses a QSocket.
    """
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = None

    def connect(self):
        self.socket = qtnetwork.QTcpSocket()
        self.socket.setSocketOption(
                qtnetwork.QAbstractSocket.LowDelayOption, True)
        self.socket.connectToHost(self.host, self.port)

    def disconnect(self):
        self.socket.close()
        self.socket = None

    def isConnected(self):
        return self.socket is None

    def sendMsg(self, msg):
        self.socket.write(msg)
        self.socket.flush()

