from slixmpp import ClientXMPP


class BoschClientXMPP(ClientXMPP):

    def __init__(self, jid, password, ssl_context=None, **kwargs):
        ClientXMPP.__init__(self, jid=jid, password=password, ssl_context=ssl_context, **kwargs)

    def connect(self, host=None, port=None):
        self.enable_direct_tls = True
        self.enable_starttls = True
        self.force_starttls = True
        return super().connect(host=host, port=port)
