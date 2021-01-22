from flask import Flask, request, redirect
from flask_restful import Resource, Api
import requests
import psutil
import time
import numpy as np
import math
import os

app = Flask(__name__)
api = Api(app)


class ReplayBuffer(object):
    def __init__(self, state_dim, batch_size, buffer_size, device):
        self.batch_size = batch_size
        self.max_size = int(buffer_size)
        self.device = device

        self.ptr = 0
        self.crt_size = 0

        self.state = np.zeros((self.max_size, state_dim))
        self.action = np.zeros((self.max_size, 1))
        self.next_state = np.array(self.state)
        self.reward = np.zeros((self.max_size, 1))
        self.not_done = np.zeros((self.max_size, 1))

    def add(self, state, action, next_state, reward, done, episode_done, episode_start):
        self.state[self.ptr] = state
        self.action[self.ptr] = action
        self.next_state[self.ptr] = next_state
        self.reward[self.ptr] = reward
        self.not_done[self.ptr] = 1. - done

        self.ptr = (self.ptr + 1) % self.max_size
        self.crt_size = min(self.crt_size + 1, self.max_size)

    def sample(self):
        ind = np.random.randint(0, self.crt_size, size=self.batch_size)
        return (
            torch.FloatTensor(self.state[ind]).to(self.device),
            torch.LongTensor(self.action[ind]).to(self.device),
            torch.FloatTensor(self.next_state[ind]).to(self.device),
            torch.FloatTensor(self.reward[ind]).to(self.device),
            torch.FloatTensor(self.not_done[ind]).to(self.device)
        )

    def save(self, save_folder):
        np.save(f"{save_folder}_state.npy", self.state[:self.crt_size])
        np.save(f"{save_folder}_action.npy", self.action[:self.crt_size])
        np.save(f"{save_folder}_next_state.npy",
                self.next_state[:self.crt_size])
        np.save(f"{save_folder}_reward.npy", self.reward[:self.crt_size])
        np.save(f"{save_folder}_not_done.npy", self.not_done[:self.crt_size])
        np.save(f"{save_folder}_ptr.npy", self.ptr)

    def load(self, save_folder, size=-1):
        reward_buffer = np.load(f"{save_folder}_reward.npy")

        # Adjust crt_size if we're using a custom size
        size = min(int(size), self.max_size) if size > 0 else self.max_size
        self.crt_size = min(reward_buffer.shape[0], size)

        self.state[:self.crt_size] = np.load(
            f"{save_folder}_state.npy")[:self.crt_size]
        self.action[:self.crt_size] = np.load(
            f"{save_folder}_action.npy")[:self.crt_size]
        self.next_state[:self.crt_size] = np.load(
            f"{save_folder}_next_state.npy")[:self.crt_size]


class Notify (Resource):
    def load_req_thres(self):
        global req_thres
        if os.path.exists("./req_thres.npy"):
            req_thres = np.load("./req_thres.npy")
            req_thres = req_thres[0]
            print("New Policy Request threshold : ", req_thres)

    def get(self):
        print("Notification of overload")
        notify = request.args.get('offload')
        self.load_req_thres()


class Greeting (Resource):
    def __init__(self, overload=10.0, offload=1.0, reward=0.2, holding=0.12, threshold_req=17):
        self.overload = overload
        self.offload = offload
        self.reward = reward
        self.holding = holding
        self.c = 2
        self.T = 0.5
        self.num_actions = 2

    def sigmoid_fn(self, cpu_util, buffer, debug=0):
        global req_thres
        # Simple as of now
        """
        If this value is > 0.5 i.e. state[0] - req_thres > 0, then we need to offload, return 1
        will high probability as a=1 for offload
        """
        # print ("State 1 ", state[1], type(state[1]))
        prob = math.exp((cpu_util - req_thres[int(buffer)])/self.T) / \
            (1 + math.exp((cpu_util - req_thres[int(buffer)])/self.T))
        if debug:
            print("Sigmoid  state, threshold, prob ",
                  state, req_thres[int(cpu_util)], prob)
        return np.random.binomial(n=1, p=prob, size=1)

    def select_action(self, cpu_util, buffer, eval_=False, debug=0):
        if np.random.uniform(0, 1) > 0.005 or eval_ == True:
            action = self.sigmoid_fn(cpu_util, buffer)
        else:
            action = np.random.randint(self.num_actions)
        if debug:
            print("ACTION : ", action)
        return action

    def get_reward(self, cpu_util, buffer, action, debug=1):
        global buff_size
        rew = 0.0
        if action == 1:
            rew -= self.offload
            print("Offload")
        if cpu_util < 3:
            if action == 1:
                rew -= self.overload
                print("Low util offload")
        elif cpu_util >= 6 and cpu_util <= 17:
            rew += self.reward
            print("Reward")
        elif cpu_util >= 18:
            rew -= self.overload
            print("Overload")
        if buffer == buff_size and action == 0:
            rew -= self.overload
            print("Buffer Full")
        rew -= self.holding * \
            (buffer - self.c) if buffer - self.c > 0 else 0
        return rew

    def get(self):
        global buff_len
        global buff_size
        global start_time
        global offload
        global buffer
        global file_count
        global load
        #packets = psutil.net_io_counters()
        #p_sent = packets.packets_sent
        #p_recv = packets.packets_recv
        count = request.args.get('count')
        #load = [x / psutil.cpu_count() * 100 for x in psutil.getloadavg()]
        #load = int(load[0]/5)
        load = psutil.cpu_percent()
        print("Load : ", load)
        load = int(load/5)
        prev_state = [buff_len, load]
        action = self.select_action(load, buff_len)
        if action == 0:
            # Perform task
            count = int(count)
            if buff_len < buff_size:
                for i in range(count):
                    time.sleep(1)
                    continue
                buff_len += 1
            #load = [x / psutil.cpu_count() * 100 for x in psutil.getloadavg()]
            #load = int(load[0]/5)
            load = psutil.cpu_percent()
            print("Load : ", load)
            load = int(load/5)
            state = [buff_len, load]
            rew = self.get_reward(load, buff_len, action)
            buffer.add(prev_state, action, state, rew, 0, 0, 0)
            if buffer.ptr == buffer.max_size - 1:
                file_count += 1
                buffer.save('buffer_' + str(file_count))
        else:
            count = request.args.get('count')
            print("Offloaded Request")
            resp = requests.get('http://172.17.0.3:3333?count=' + count)
            #load = [x / psutil.cpu_count() * 100 for x in psutil.getloadavg()]
            #load = int(load[0]/5)
            load = psutil.cpu_percent()
            print("Load : ", load)
            load = int(load/5)
            state = [buff_len, load]
            rew = self.get_reward(load, buff_len, action)
            buffer.add(prev_state, action, state, rew, 0, 0, 0)
            if buffer.ptr == buffer.max_size - 1:
                file_count += 1
                buffer.save('buffer_' + str(file_count))
        print("ARRIVAL State, Action Next_state Reward",
              prev_state, action, state, rew)
        prev_state = [buff_len, load]
        action = self.select_action(load, buff_len)
        buff_len = max(buff_len - 1, 0)
        load = psutil.cpu_percent()
        print("Load : ", load)
        load = int(load/5)
        #load = [x / psutil.cpu_count() * 100 for x in psutil.getloadavg()]
        #load = int(load[0] / 5)
        rew = self.get_reward(load, buff_len, action)
        state = [buff_len, load]
        buffer.add(prev_state, action, state, rew, 0, 0, 0)
        print("DEPT State, Action Next_state Reward",
              prev_state, action, state, rew)
        if buffer.ptr == buffer.max_size - 1:
            file_count += 1
            buffer.save('buffer_' + str(file_count))
        return [file_count, buffer.ptr]


buff_size = 20
file_count = 0
buff_len = 0
offload = 0
load = 0
batch_size = 100
replay_size = 100
state_dim = 2
threshold_req = 17
start_time = time.time()
buffer = ReplayBuffer(state_dim, batch_size, replay_size, 'cpu')
req_thres = np.full((21), threshold_req, dtype=float)
api.add_resource(Greeting, '/')  # Route_1
api.add_resource(Notify, '/notify')  # Route_2

if __name__ == '__main__':
    app.run('0.0.0.0', '3333')
