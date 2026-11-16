"""Puts the page in the site repo, filled in from settings.json.

  python make_page.py                 the first time
  python make_page.py --skriv-over    after changing the settings or
                                       getting a new version of the page

website_creator.py runs this for you. It copies ../page/index.html (a plain
page; restyle it as you like) to <webbrepo>/<undermapp>/ and fills in the
placeholders: the site's name and address, the key's link code (ref), the
shop's character and the time zone. It does not commit; sync.py and
website_creator.py do.
"""
import datetime
import os
import sys
import urllib.parse

import settings as inst

HERE = os.path.dirname(os.path.abspath(__file__))
MALL = os.path.join(HERE, "..", "page")


def main(args):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if not inst.WEB or not os.path.isdir(inst.WEB):
        sys.exit("webbrepo in settings.json does not exist: %r" % inst.WEB)
    ut = inst.sida()
    fil = os.path.join(ut, "index.html")
    if os.path.exists(fil) and "--skriv-over" not in args:
        sys.exit("%s already exists. Run with --skriv-over to replace it." % fil)
    if not inst.REF:
        print("NOTE: ref is missing in settings.json. maplestory.market's API terms want the key's "
              "link code (?ref=...) in the links to them; it is on your Account page there.")
    varden = {
        "{{SAJTNAMN}}": inst.SAJTNAMN,
        "{{SAJT_URL}}": inst.SAJT_URL,
        "{{REF_Q}}": "?ref=" + urllib.parse.quote(inst.REF) if inst.REF else "",
        "{{BUTIK}}": urllib.parse.quote(inst.BUTIK),
        "{{TIDSZON}}": inst.TIDSZON_NAMN,
        "{{AR}}": str(datetime.date.today().year),
    }
    html = open(os.path.join(MALL, "index.html"), encoding="utf-8").read()
    for k, v in varden.items():
        html = html.replace(k, v.replace("&", "&amp;").replace("<", "&lt;").replace("'", "&#39;")
                            if k == "{{SAJTNAMN}}" else v)
    os.makedirs(os.path.join(ut, "data"), exist_ok=True)
    os.makedirs(os.path.join(ut, "icons"), exist_ok=True)
    with open(fil, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print("the page is in", ut)


if __name__ == "__main__":
    main(sys.argv[1:])
