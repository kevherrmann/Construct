"""E-Mail: Server eigener Domains erkennen (MX, Thunderbird-Datenbank, von Hand).

Ohne Netz: DNS und HTTP werden ersetzt. Die Konten-Datei liegt im tmp-Ordner.
"""
import pytest

from server import mail

STRATO_XML = b"""<clientConfig version="1.1"><emailProvider id="strato.de">
<displayShortName>Strato</displayShortName>
<incomingServer type="pop3"><hostname>pop3.strato.de</hostname><port>995</port>
 <socketType>SSL</socketType><authentication>password-cleartext</authentication></incomingServer>
<incomingServer type="imap"><hostname>imap.strato.de</hostname><port>143</port>
 <socketType>STARTTLS</socketType><authentication>password-cleartext</authentication>
 <username>%EMAILADDRESS%</username></incomingServer>
<incomingServer type="imap"><hostname>imap.strato.de</hostname><port>993</port>
 <socketType>SSL</socketType><authentication>password-cleartext</authentication>
 <username>%EMAILADDRESS%</username></incomingServer>
<outgoingServer type="smtp"><hostname>smtp.strato.de</hostname><port>25</port>
 <socketType>plain</socketType><authentication>password-cleartext</authentication></outgoingServer>
<outgoingServer type="smtp"><hostname>smtp.strato.de</hostname><port>587</port>
 <socketType>STARTTLS</socketType><authentication>password-cleartext</authentication></outgoingServer>
</emailProvider></clientConfig>"""


@pytest.fixture(autouse=True)
def _offline(tmp_path, monkeypatch):
    monkeypatch.setattr(mail, "ACC_FILE", tmp_path / ".mail-accounts.json")
    monkeypatch.setattr(mail, "_mx_hosts", lambda d: [])
    monkeypatch.setattr(mail, "_http_get", lambda url, limit=65536: (_ for _ in ()).throw(OSError(url)))


def test_bekannte_endung_ohne_netz():
    p = mail.detect("a@gmx.de")
    assert p["name"] == "GMX" and p["source"] == "Adresse"
    assert tuple(p["imap"]) == ("imap.gmx.net", 993, "SSL")


def test_mx_google_ist_workspace_und_schlaegt_autoconfig(monkeypatch):
    # nils-digital.de: Domain bei Strato (autoconfig zeigt dorthin), Mails bei Google.
    monkeypatch.setattr(mail, "_mx_hosts", lambda d: ["aspmx.l.google.com"])
    monkeypatch.setattr(mail, "_http_get", lambda url, limit=65536: STRATO_XML)
    p = mail.detect("kevin@firma.de")
    assert p["name"] == "Google Workspace" and p["kind"] == "gmail" and p["source"] == "MX"


def test_mx_microsoft_365_meldet_sich_bei_organizations(monkeypatch):
    monkeypatch.setattr(mail, "_mx_hosts", lambda d: ["firma-de.mail.protection.outlook.com"])
    p = mail.detect("a@firma.de")
    assert p["auth"] == "oauth" and p["tenant"] == "organizations"
    assert "/organizations/" in mail._ms_url({"email": "a@firma.de", "server": p}, "token")
    assert "/consumers/" in mail._ms_url({"email": "a@hotmail.com"}, "token")


def test_mx_eigener_host_ist_auch_der_server(monkeypatch):
    monkeypatch.setattr(mail, "_mx_hosts", lambda d: ["w0123456.kasserver.com"])
    p = mail.detect("a@firma.de")
    assert tuple(p["imap"]) == ("w0123456.kasserver.com", 993, "SSL")
    assert tuple(p["smtp"]) == ("w0123456.kasserver.com", 465, "SSL")


def test_mx_endung_nur_an_punktgrenze(monkeypatch):
    monkeypatch.setattr(mail, "_mx_hosts", lambda d: ["mx.evilgoogle.com"])
    assert mail.detect("a@firma.de") is None


def test_thunderbird_datenbank_nimmt_verschluesselte_imap_und_smtp(monkeypatch):
    urls = []

    def get(url, limit=65536):
        urls.append(url)
        if url.endswith("/v1.1/firma.de"):
            return STRATO_XML
        raise OSError(url)

    monkeypatch.setattr(mail, "_http_get", get)
    p = mail.detect("a@firma.de")
    assert p["source"] == "Thunderbird-Datenbank" and p["name"] == "Strato"
    assert tuple(p["imap"]) == ("imap.strato.de", 993, "SSL")       # SSL vor STARTTLS
    assert tuple(p["smtp"]) == ("smtp.strato.de", 587, "STARTTLS")  # plain fällt raus
    assert p["user"] == ""                                          # = die Adresse
    assert urls == ["https://autoconfig.thunderbird.net/v1.1/firma.de"]


def test_autoconfig_ohne_passende_server_zaehlt_nicht():
    xml = b"<clientConfig><emailProvider><incomingServer type='imap'><hostname>x.de</hostname>" \
          b"<port>143</port><socketType>plain</socketType></incomingServer></emailProvider></clientConfig>"
    assert mail._parse_autoconfig(xml, "a@b.de") is None
    assert mail._parse_autoconfig(b"<kaputt", "a@b.de") is None


def test_unbekannt_verlangt_server_von_hand():
    with pytest.raises(mail.NeedServer):
        mail.save_account("a@niemand.de", "pw")
    assert mail.load_accounts() == []


def test_von_hand_eintragen_und_spaeter_nur_passwort_aendern(monkeypatch):
    r = mail.save_account("A@Firma.de", "pw", {"imap_host": "Mail.Firma.de", "imap_port": "993",
                                              "smtp_host": "mail.firma.de", "smtp_port": 587,
                                              "user": "m0123"})
    assert r["provider"] == "Eigener Server"
    acc = mail.account("a@firma.de")
    p = mail.provider_of(acc)
    assert tuple(p["imap"]) == ("mail.firma.de", 993, "SSL")
    assert tuple(p["smtp"]) == ("mail.firma.de", 587, "STARTTLS")
    assert mail._login_name(acc, p) == "m0123"

    # Neues Passwort: die Server bleiben, es wird nicht neu gesucht.
    monkeypatch.setattr(mail, "detect", lambda a: pytest.fail("darf nicht neu suchen"))
    mail.save_account("a@firma.de", "neu")
    acc = mail.account("a@firma.de")
    assert acc["password"] == "neu" and tuple(mail.provider_of(acc)["imap"])[0] == "mail.firma.de"

    pub = mail.public_accounts()[0]
    assert pub["imap"] == "mail.firma.de:993" and "password" not in pub and "user" not in pub


@pytest.mark.parametrize("bad", [
    {"imap_host": "", "smtp_host": "s.de"},
    {"imap_host": "http://x.de", "smtp_host": "s.de"},
    {"imap_host": "x.de", "smtp_host": "s.de", "smtp_port": "99999"},
    {"imap_host": "x.de", "smtp_host": "s.de", "imap_port": "abc"},
])
def test_von_hand_prueft_eingaben(bad):
    with pytest.raises(mail.MailError):
        mail.save_account("a@firma.de", "pw", bad)


def test_alte_konten_ohne_server_nutzen_die_endung(tmp_path):
    mail._write_accounts([{"email": "x@hotmail.com", "ms_refresh": "r"}])
    p = mail.provider_of(mail.account("x@hotmail.com"))
    assert p["auth"] == "oauth" and p["kind"] == "outlook"
    pub = mail.public_accounts()[0]
    assert pub["provider"] == "Outlook/Hotmail" and pub["configured"]


def test_api_meldet_fehlende_server(client):
    r = client.post("/api/mail/accounts", json={"email": "a@niemand.de", "password": "pw"})
    assert r.status_code == 400 and r.json()["need_server"] is True


@pytest.mark.parametrize("addr", ["a@b", "a@127.0.0.1:8765", "a@x.de/pfad", "kein-at.de"])
def test_adresse_muss_echte_domain_haben(addr, monkeypatch):
    monkeypatch.setattr(mail, "detect", lambda a: pytest.fail("darf nicht suchen"))
    with pytest.raises(mail.MailError, match="Keine gültige"):
        mail.save_account(addr, "pw")
