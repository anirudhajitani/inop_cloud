import random
import time
import subprocess
from random import randrange
import sys
import re
from multiprocessing import Process
import threading as th
import numpy as np
import pickle

ip_address = '172.17.0.2'
port = '3333'
container_name = 'app1'
folder = sys.argv[1]
env_name = sys.argv[2]
fc = 0
res_path = f'./{folder}/results/rewards_{env_name}.npy'
results = []

def fireEvent(start_time):
    global fc
    x = randrange(0, 1)
    print (x, time.time() - start_time)
    q_str = 'http://' + ip_address + ':' + port + '?' + 'count=' + str(x)
    out = subprocess.Popen(['docker', 'run', '--rm', 'byrnedo/alpine-curl', '-s', q_str],
    #out = subprocess.Popen(['docker', 'run', '--rm', 'byrnedo/alpine-curl', '-w', '@curlformat', '-s', q_str],
    #out = subprocess.Popen(['docker', 'run', '--rm', 'curl_client', '-w', '@curlformat', '-o', '/dev/null', '-s', q_str],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()
    print(stdout)
    print(stderr)
    # Get new FC from stdout

def run_rl_module_and_notify(fc):
    dest_path_str = container_name + ':/req_thres.npy'
    src_path_str = f'./{folder}/buffers/thresvec_{env_name}_{str(fc)}.npy'
    out = subprocess.Popen(['docker', 'cp', src_path_str, dest_path_str],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()
    print(stdout)
    print(stderr)
    q_str = 'http://' + ip_address + ':' + port + '/notify?' + 'offload=0'
    #out = subprocess.Popen(['docker', 'run', '--rm', 'byrnedo/alpine-curl', '-w', '@curlformat', '-s', q_str],
    out = subprocess.Popen(['docker', 'run', '--rm', 'byrnedo/alpine-curl', '-s', q_str],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()
    stdout = stdout.decode('utf-8')
    op = re.split('\n|\"', stdout)
    print(stdout)
    print(stderr)
    print("Ouput ", op, " OP ", op[1])
    results.append(float(op[1]))
    np.save(res_path, results)


def process_event(lambd):
    start_time = time.time()
    while time.time() - start_time < 30:
        #interval = random.expovariate(0.1)
        interval = random.expovariate(lambd)
        time.sleep(interval)
        fireEvent(start_time)


def main():
    fc = 0
    with open(f"./{folder}/buffers/lambda.npy", "rb") as fp:
        lambd = pickle.load(fp)
    with open(f"./{folder}/buffers/N.npy", "rb") as fp:
        N = pickle.load(fp)
    for l in range(1000):
        jobs = []
        if l > 0:
            run_rl_module_and_notify(l)
        for i in range(N[l]):
            print (lambd[l][i])
            t = th.Thread(target=process_event, args=(lambd[l][i],))
            jobs.append(t)
        for j in jobs:
            j.start()
        for j in jobs:
            j.join()


if __name__ == "__main__":
    main()
