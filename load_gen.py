import random
import time
import subprocess
from random import randrange
import sys
import re
from multiprocessing import Process
import threading as th
import pickle

ip_address = '172.17.0.2'
port = '3333'
container_name = 'app1'
folder = sys.argv[1]
env_name = sys.argv[2]
fc = 0


def fireEvent(start_time):
    global fc
    x = randrange(0, 1)
    #print (x, time.time() - start_time)
    q_str = 'http://' + ip_address + ':' + port + '?' + 'count=' + str(x)
    out = subprocess.Popen(['docker', 'run', '--rm', 'byrnedo/alpine-curl', '-s', q_str],
    #out = subprocess.Popen(['docker', 'run', '--rm', 'byrnedo/alpine-curl', '-w', '@curlformat', '-s', q_str],
    #out = subprocess.Popen(['docker', 'run', '--rm', 'curl_client', '-w', '@curlformat', '-o', '/dev/null', '-s', q_str],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()
    stdout = stdout.decode('utf-8')
    op = re.split('\[|, ', stdout)
    print(op)
    #print("Output ", op[1])
    print(stdout)
    print(stderr)
    # Get new FC from stdout
    new_fc = int(op[1])
    if new_fc > fc:
        fc = new_fc
        run_rl_module_and_notify(fc)


def run_rl_module_and_notify(fc, run):
    print ("Notification module called")
    q_str = 'http://' + ip_address + ':' + port + '/notify?' + 'offload=' + str(-run)
    #out = subprocess.Popen(['docker', 'run', '--rm', 'curl_client', '-w', '@curlformat', '-s', q_str],
    out = subprocess.Popen(['docker', 'run', '--rm', 'byrnedo/alpine-curl', '-s', q_str],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()
    #print(stdout)
    #print(stderr)
    if fc == 0:
        return

    q_str = 'http://' + ip_address + ':' + port + '/notify?' + 'offload=' + str(fc)
    #out = subprocess.Popen(['docker', 'run', '--rm', 'curl_client', '-w', '@curlformat', '-s', q_str],
    out = subprocess.Popen(['docker', 'run', '--rm', 'byrnedo/alpine-curl', '-s', q_str],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()
    #print(stdout)
    #print(stderr)
    files_dst = ['_ptr.npy', '_state.npy', '_next_state.npy',
                 '_action.npy', '_reward.npy', '_not_done.npy'] 
    files_dst_2 = ['overload_count.npy', 'offload_count.npy']
    dest_path_str = folder + '/buffers/'
    for file_dst in files_dst:
        path_str = container_name + ':/buffer_' + str(run) + '_' + str(fc) + file_dst
        out = subprocess.Popen(['docker', 'cp', path_str, dest_path_str],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
        stdout, stderr = out.communicate()
        #print(stdout)
        #print(stderr)
    for file_dst in files_dst_2:
        path_str = container_name + ':/buffer_' + str(run) + '_' + file_dst
        out = subprocess.Popen(['docker', 'cp', path_str, dest_path_str],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
        stdout, stderr = out.communicate()
        #print(stdout)
        #print(stderr)
    buffer_name = 'buffer_' + str(run) + '_' + str(fc)
    out = subprocess.Popen(['python3.7', 'main_train.py', '--replay_buffer', buffer_name, '--fc', str(fc), 
                            '--run', str(run), '--algo', '3', '--folder', folder, '--env_name', env_name],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()
    #print(stdout)
    #print(stderr)
    dest_path_str = container_name + ':/req_thres.npy'
    src_path_str = f'./{folder}/buffers/thresvec_{str(run)}_{env_name}_{str(fc)}.npy'
    out = subprocess.Popen(['docker', 'cp', src_path_str, dest_path_str],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()
    #print(stdout)
    #print(stderr)
    q_str = 'http://' + ip_address + ':' + port + '/notify?' + 'offload=0'
    #out = subprocess.Popen(['docker', 'run', '--rm', 'curl_client', '-w', '@curlformat', '-s', q_str],
    out = subprocess.Popen(['docker', 'run', '--rm', 'byrnedo/alpine-curl', '-s', q_str],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()
    #print(stdout)
    #print(stderr)
    print("NOTIF completed")
    return

def process_event(lambd):
    start_time = time.time()
    while time.time() - start_time < 100:
        #interval = random.expovariate(0.1)
        interval = random.expovariate(lambd)
        interval = min(interval, 20.0)
        time.sleep(interval)
        fireEvent(start_time)

def main():
    fc = 0
    with open(f"./{folder}/buffers/lambda.npy", "rb") as fp:
        lambd = pickle.load(fp)
    with open(f"./{folder}/buffers/N.npy", "rb") as fp:
        N = pickle.load(fp)
    for run in range(1,6):
        random.seed(run)
        start_loop = 0
        for l in range(start_loop, 1000):
            print("RUN = ", run, " LOOP = ", l)
            jobs = []
            run_rl_module_and_notify(l, run)
            for i in range(N[l]):
                #print (lambd[l][i])
                t = th.Thread(target=process_event, args=(lambd[l][i],))
                jobs.append(t)
            for j in jobs:
                j.start()
            for j in jobs:
                j.join(timeout=20)
            print("LOOP ", l, " complete ")


if __name__ == "__main__":
    main()
