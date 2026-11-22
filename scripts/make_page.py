"""Puts the page in the site repo, filled in from settings.json.

  python make_page.py                 the first time
  python make_page.py --overwrite     after changing the settings or
                                      getting a new version of the page

website_creator.py runs this for you. It copies ../page/index.html (a plain
page; restyle it as you like) to <site_repo>/<subfolder>/ and fills in the
placeholders: the site's name and address, the key's link code (ref) and
the time zone. It does not commit; sync.py and
website_creator.py do.
"""
import datetime
import os
import sys
import urllib.parse

import settings as cfg

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "page")


def main(args):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if not cfg.WEB or not os.path.isdir(cfg.WEB):
        sys.exit("site_repo in settings.json does not exist: %r" % cfg.WEB)
    out = cfg.page_dir()
    path = os.path.join(out, "index.html")
    if os.path.exists(path) and "--overwrite" not in args and "--skriv-over" not in args:
        sys.exit("%s already exists. Run with --overwrite to replace it." % path)
    if not cfg.REF:
        print("NOTE: ref is missing in settings.json. maplestory.market's API terms want the key's "
              "link code (?ref=...) in the links to them; it is on your Account page there.")
    values = {
        "{{SITE_NAME}}": cfg.SITE_NAME,
        "{{SITE_URL}}": cfg.SITE_URL,
        "{{REF_Q}}": "?ref=" + urllib.parse.quote(cfg.REF) if cfg.REF else "",
        "{{TIME_ZONE}}": cfg.TIME_ZONE_NAME,
        "{{YEAR}}": str(datetime.date.today().year),
    }
    html = open(os.path.join(TEMPLATE, "index.html"), encoding="utf-8").read()
    for k, v in values.items():
        html = html.replace(k, v.replace("&", "&amp;").replace("<", "&lt;").replace("'", "&#39;")
                            if k == "{{SITE_NAME}}" else v)
    os.makedirs(os.path.join(out, "data"), exist_ok=True)
    os.makedirs(os.path.join(out, "icons"), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print("the page is in", out)


if __name__ == "__main__":
    main(sys.argv[1:])
