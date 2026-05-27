import flask


class ScriptNameFix:
    def __init__(self, app, script_name):
        self.app = app
        self.script_name = script_name

    def __call__(self, environ, start_response):
        environ["SCRIPT_NAME"] = self.script_name
        path = environ.get("PATH_INFO", "")
        if path.startswith(self.script_name):
            environ["PATH_INFO"] = path[len(self.script_name) :]
        return self.app(environ, start_response)


app = flask.Flask(__name__)
app.config["APPLICATION_ROOT"] = "/polls"
app.wsgi_app = ScriptNameFix(app.wsgi_app, "/polls")


@app.route("/debug")
def hello():
    r = flask.request
    return f"{r.url=}<br>script name: {r.environ.get('SCRIPT_NAME')}<br>path_info: {r.environ.get('PATH_INFO')}"
