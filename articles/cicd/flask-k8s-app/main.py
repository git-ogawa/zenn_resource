#!/usr/bin/env python
import os

from flask import Flask, jsonify

app = Flask(__name__)

region = os.getenv("REGION", "default")
cluster = os.getenv("CLUSTER", "undefined")


@app.route("/")
def hello_world():
    ret = {"message": f"This is {region}", "cluster": cluster}
    return jsonify(ret)


if __name__ == "__main__":
    app.run(host="0.0.0.0")
