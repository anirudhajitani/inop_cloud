from flask import Flask, request, redirect
from flask_restful import Resource, Api
import requests

app = Flask(__name__)
api = Api(app)
notify = Flask(__name__)
notify_api = Api(app)


class Notify (Resource):
    def get(self):
        notify = request.args.get('offload')
        return int(notify)
        try:
            f = open("policy.txt", "r")
            c = f.read()
            c = int(c)
            notify = int(notify)
            if notify == c:
                f.close()
                return c
            else:
                f = open("policy.txt", "w")
                f.write(str(notify))
                f.close()
                return notify
        except:
            f = open("policy.txt", "w")
            f.write(str(notify))
            f.close()
            return notify


class Greeting (Resource):
    def get(self):
        try:
            f = open("policy.txt", "r")
            c = f.read()
            offload = int(c)
        except:
            offload = 1
        if offload == 0:
            count = request.args.get('count')
            count = int(count)
            for i in range(count):
                continue
            return count
        else:
            count = request.args.get('count')
            #redirect_str = "http://172.17.0.3:3333?count=" + count
            resp = requests.get('http://172.17.0.3:3333?count=' + count)
            return resp.text
            # return redirect(redirect_str, code=302)


api.add_resource(Greeting, '/')  # Route_1
notify_api.add_resource(Notify, '/')  # Route_1

if __name__ == '__main__':
    app.run('0.0.0.0', '3333')
    notify.run('0.0.0.0', '6666')
