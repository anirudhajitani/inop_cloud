import random
import time
import subprocess
from random import randrange
import sys
import re
"""
from multiprocessing import Process
import threading as th
import pickle
"""

ip_address = '172.17.0.2'
port = '3333'
container_name = 'app1'
start_time = time.time()
folder = sys.argv[1]
env_name = sys.argv[2]


def fireEvent(fc):
    x = randrange(0, 1)
    print (x, time.time() - start_time)
    q_str = 'http://' + ip_address + ':' + port + '?' + 'count=' + str(x)
    out = subprocess.Popen(['docker', 'run', '--rm', 'curl_client', '-w', '@curlformat', '-s', q_str],
                           # out = subprocess.Popen(['docker', 'run', '--rm', 'curl_client', '-w', '@curlformat', '-o', '/dev/null', '-s', q_str],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()
    stdout = stdout.decode('utf-8')
    op = re.split('\[|, ', stdout)
    # print(op)
    # print(op[1])
    print(stdout)
    print(stderr)
    # Get new FC from stdout
    new_fc = int(op[1])
    if new_fc > fc:
        fc = new_fc
        files_dst = ['_ptr.npy', '_state.npy', '_next_state.npy',
                     '_action.npy', '_reward.npy', '_not_done.npy']
        dest_path_str = folder + '/buffers/'
        for file_dst in files_dst:
            path_str = container_name + ':/buffer_' + str(fc) + file_dst
            out = subprocess.Popen(['docker', 'cp', path_str, dest_path_str],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
            stdout, stderr = out.communicate()
            print(stdout)
            print(stderr)
        buffer_name = 'buffer_' + str(fc)
        out = subprocess.Popen(['python3', 'main_train.py', '--replay_buffer', buffer_name, '--fc', str(fc), '--algo', '3', '--folder', folder, '--env_name', env_name],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
        stdout, stderr = out.communicate()
        print(stdout)
        print(stderr)
        dest_path_str = container_name + ':/req_thres.npy'
        src_path_str = f'./{folder}/buffers/thresvec_{env_name}_{str(fc)}.npy'
        out = subprocess.Popen(['docker', 'cp', src_path_str, dest_path_str],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
        stdout, stderr = out.communicate()
        print(stdout)
        print(stderr)
        q_str = 'http://' + ip_address + ':' + port + '/notify?' + 'offload=1'
        out = subprocess.Popen(['docker', 'run', '--rm', 'curl_client', '-w', '@curlformat', '-s', q_str],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
        stdout, stderr = out.communicate()
        print(stdout)
        print(stderr)
    return fc


def main():
    fc = 0
    """
    with open (f"./{folder}/buffers/lambda.npy", "rb") as fp:
    	lambd = pickle.load(fp)
    with open (f"./{folder}/buffers/N.npy", "rb") as fp:
        N = pickle.load(fp)
    for i in range(N):    
	t = th.Thread(target=process_event, args=(lambd, i)) 
    """
    while True:
        interval = random.expovariate(0.5)
        time.sleep(interval)
        fc = fireEvent(fc)


if __name__ == "__main__":
    main()
