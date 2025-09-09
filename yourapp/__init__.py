# yourapp/__init__.py
import importlib
import pkgutil
from flask import Flask, render_template, Response, url_for

from . import registry

def create_app():
    app = Flask(__name__)

    # Auto-discover and register all blueprints: yourapp.tools.<module>.routes:bp
    from . import tools
    for _finder, name, _ispkg in pkgutil.iter_modules(tools.__path__, tools.__name__ + "."):
        try:
            mod = importlib.import_module(f"{name}.routes")
            bp = getattr(mod, "bp", None)
            if bp:
                app.register_blueprint(bp)
        except ModuleNotFoundError:
            pass  # module without routes.py is fine

    # Home – renders cards from registry
    @app.get("/")
    def home():
        return render_template("home.html", tools=registry.TOOLS)

    # robots.txt
    @app.get("/robots.txt")
    def robots():
        lines = [
            "User-agent: *",
            "Allow: /",
            f"Sitemap: {url_for('sitemap', _external=True)}",
        ]
        return Response("\n".join(lines), mimetype="text/plain")

    # sitemap.xml – includes home and tool URLs from registry
    @app.get("/sitemap.xml")
    def sitemap():
        urls = [url_for('home', _external=True)]
        urls += [t["absolute_url"] for t in registry.TOOLS]
        xml = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]
        xml += [f"<url><loc>{u}</loc></url>" for u in urls]
        xml.append("</urlset>")
        return Response("\n".join(xml), mimetype="application/xml")

    return app
