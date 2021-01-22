import argparse
import copy
import importlib
import json
import os
import statistics
import numpy as np
import torch
import random
#import discrete_BCQ
import structured_learning
#import DQN
import time
from NewOffloadEnv import OffloadEnv
from stable_baselines3.common.vec_env.dummy_vec_env import DummyVecEnv
#from OffloadEnv2 import OffloadEnv
import utils
import pickle
from stable_baselines3.common.cmd_util import make_vec_env
import matplotlib.pyplot as plt
from stable_baselines3 import TD3
from stable_baselines3.common.results_plotter import load_results, ts2xy
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3 import DQN, SAC
from stable_baselines3 import A2C, PPO
#from stable_baselines.common.vec_env import DummyVecEnv
#from stable_baselines import DQN
from stable_baselines3.common import results_plotter


def interact_with_environment(env, replay_buffer, is_atari, num_actions, state_dim, device, args, parameters):
    # For saving files
    setting = f"{args.env}_{args.seed}"
    buffer_name = f"{args.buffer_name}_{setting}"
    #setting = args.env + "_" + args.seed
    #buffer_name = args.buffer_name + "_" + setting

    # Initialize and load policy
    policy = DQN.DQN(
        is_atari,
        num_actions,
        state_dim,
        device,
        parameters["discount"],
        parameters["optimizer"],
        parameters["optimizer_parameters"],
        parameters["polyak_target_update"],
        parameters["target_update_freq"],
        parameters["tau"],
        parameters["initial_eps"],
        parameters["end_eps"],
        parameters["eps_decay_period"],
        parameters["eval_eps"],
    )

    if args.generate_buffer:
        policy.load(f"./models/behavioral_{setting}")

    evaluations = []

    state, done = env.reset(), False
    episode_start = True
    episode_reward = 0
    episode_timesteps = 0
    episode_num = 0
    low_noise_ep = np.random.uniform(0, 1) < args.low_noise_p

    # Interact with the environment for max_timesteps
    for t in range(int(args.max_timesteps)):

        episode_timesteps += 1

        # If generating the buffer, episode is low noise with p=low_noise_p.
        # If policy is low noise, we take random actions with p=eval_eps.
        # If the policy is high noise, we take random actions with p=rand_action_p.
        if args.generate_buffer:
            if not low_noise_ep and np.random.uniform(0, 1) < args.rand_action_p - parameters["eval_eps"]:
                action = np.random.binomial(n=1, p=0.5, size=1)[0]
            else:
                action = policy.select_action(np.array(state), eval=True)

        if args.train_behavioral:
            if t < parameters["start_timesteps"]:
                action = np.random.binomial(n=1, p=0.5, size=1)[0]
            else:
                action = policy.select_action(np.array(state))

        # Perform action and log results
        next_state, reward, done, info = env.step(action)
        episode_reward += reward

        # Only consider "done" if episode terminates due to failure condition
        done_float = float(
            done) if episode_timesteps < env._max_episode_steps else 0

        # For atari, info[0] = clipped reward, info[1] = done_float
        if is_atari:
            reward = info[0]
            done_float = info[1]

        # Store data in replay buffer
        replay_buffer.add(state, action, next_state, reward,
                          done_float, done, episode_start)
        state = copy.copy(next_state)
        episode_start = False

        # Train agent after collecting sufficient data
        if args.train_behavioral and t >= parameters["start_timesteps"] and (t+1) % parameters["train_freq"] == 0:
            policy.train(replay_buffer)

        if done:
            # +1 to account for 0 indexing. +0 on ep_timesteps since it will increment +1 even if done=True
            print(
                f"Total T: {t+1} Episode Num: {episode_num+1} Episode T: {episode_timesteps} Reward: {episode_reward:.3f}")
            # Reset environment
            state, done = env.reset(), False
            episode_start = True
            episode_reward = 0
            episode_timesteps = 0
            episode_num += 1
            low_noise_ep = np.random.uniform(0, 1) < args.low_noise_p

        # Evaluate episode
        if args.train_behavioral and (t + 1) % parameters["eval_freq"] == 0:
            evaluations.append(eval_policy(policy, args.env, args.seed))
            np.save(f"./results/behavioral_{setting}", evaluations)
            policy.save(f"./models/behavioral_{setting}")

    # Save final policy
    if args.train_behavioral:
        policy.save(f"./models/behavioral_{setting}")

    # Save final buffer and performance
    else:
        evaluations.append(eval_policy(policy, args.env, args.seed))
        np.save(f"./results/buffer_performance_{setting}", evaluations)
        replay_buffer.save(f"./buffers/{buffer_name}")


# Trains BCQ offline
def train_salmut_reset(env, policy, steps, args):
    # For saving files
    setting = f"{args.env}_{args.seed}"
    training_evaluations = []
    episode_num = 0
    avg_reward = 0.0
    done = True
    training_iters = 0
    state = env.reset()
    for _ in range(int(args.eval_freq)):
        action = policy.select_action(state)
        prev_state = state
        state, reward, done, _ = env.step(action)
        avg_reward += reward
        if done:
            training_eval.append(avg_reward)
            avg_reward = 0.0
            np.save(
                f"./{args.folder}/results/salmut_train_{setting}", training_eval)
        policy.train(prev_state, action, reward, state,
                     args.eval_freq, args.env_name, args.folder)


def train_salmut(env, policy, steps, args, state, j):
    # For saving files
    setting = f"{args.env_name}_{j}"
    training_evaluations = []
    episode_num = 0
    avg_reward = 0.0
    done = True
    training_iters = 0
    #state = env.reset()
    for _ in range(int(args.eval_freq)):
        action = policy.select_action(state)
        #print ("Action ", action)
        prev_state = state
        state, reward, done, _ = env.step(action)
        avg_reward += reward
        if done:
            training_eval.append(avg_reward)
            avg_reward = 0.0
            np.save(
                f"./{args.folder}/results/salmut_train_{setting}", training_eval)
        policy.train(prev_state, action, reward, state,
                     args.eval_freq, args.env_name, args.folder, j)
    return state

# Runs policy for X episodes and returns average reward
# A fixed seed is used for the eval environment


def eval_policy(policy, env_name, seed, type=0, eval_episodes=1000, threshold_pol=7):
    #eval_env, _, _, _ = utils.make_env(env_name, atari_preprocessing)
    #eval_env.seed(seed + 100)
    global cpu_util
    global action_list
    eval_env = OffloadEnv()
    avg_reward = 0.
    for _ in range(eval_episodes):
        state, done = eval_env.reset(), False
        for t in range(200):
            if type == 0:
                action = policy.select_action(np.array(state), eval=True)
            elif type == 1:
                if state[1] < threshold_pol:
                    action = 0
                else:
                    action = 1
            prev_state = state
            # cpu_util.append(state[1])
            # action_list.append(action)
            state, reward, done, _ = eval_env.step(action)
            avg_reward += reward
            print("Eval policy action reward",
                  prev_state, action, reward, state)

    avg_reward /= eval_episodes

    print("---------------------------------------")
    print(f"Evaluation over {eval_episodes} episodes: {avg_reward:.3f}")
    print("---------------------------------------")
    #cpu_npy = np.array(cpu_util)
    #act_npy = np.array(action_list)
    #np.save('./buffers/cpu_util.npy', cpu_npy)
    #np.save('./buffers/action.npy', act_npy)
    return avg_reward


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


if __name__ == "__main__":

    # Atari Specific
    atari_preprocessing = {
        "frame_skip": 4,
        "frame_size": 84,
        "state_history": 4,
        "done_on_life_loss": False,
        "reward_clipping": True,
        "max_episode_timesteps": 27e3
    }

    atari_parameters = {
        # Exploration
        "start_timesteps": 2e4,
        "initial_eps": 1,
        "end_eps": 1e-2,
        "eps_decay_period": 25e4,
        # Evaluation
        "eval_freq": 5e3,
        "eval_eps": 1e-3,
        # Learning
        "discount": 0.99,
        "buffer_size": 1e6,
        "batch_size": 32,
        "optimizer": "Adam",
        "optimizer_parameters": {
            "lr": 0.0000625,
            "eps": 0.00015
        },
        "train_freq": 4,
        "polyak_target_update": False,
        "target_update_freq": 8e3,
        "tau": 1
    }

    regular_parameters = {
        # Exploration
        "start_timesteps": 1e3,
        "initial_eps": 0.1,
        "end_eps": 0.1,
        "eps_decay_period": 1,
        # Evaluation
        "eval_freq": 1e4,
        "eval_eps": 0,
        # Learning
        "discount": 0.999,
        "buffer_size": 1e6,
        "batch_size": 1000,
        "optimizer": "Adam",
        "optimizer_parameters": {
            "lr": 3e-4
        },
        "train_freq": 1,
        "polyak_target_update": False,
        "target_update_freq": 1,
        "tau": 0.005
    }
    start_time = time.time()
    # Load parameters
    parser = argparse.ArgumentParser()
    # OpenAI gym environment name
    parser.add_argument("--env", default="PongNoFrameskip-v0")
    # Sets Gym, PyTorch and Numpy seeds
    parser.add_argument("--seed", default=20, type=int)
    # Prepends name to filename
    parser.add_argument("--buffer_name", default="offload_0310")
    # Max time steps to run environment or train for
    parser.add_argument("--max_timesteps", default=1e6, type=int)
    # Threshold hyper-parameter for BCQ
    parser.add_argument("--BCQ_threshold", default=0.3, type=float)
    # Probability of a low noise episode when generating buffer
    parser.add_argument("--low_noise_p", default=0.2, type=float)
    # Probability of taking a random action when generating buffer, during non-low noise episode
    parser.add_argument("--rand_action_p", default=0.2, type=float)
    # If true, train behavioral policy
    parser.add_argument("--train_behavioral", action="store_true")
    # If true, generate buffer
    parser.add_argument("--generate_buffer", action="store_true")
    # Algo 0-PPO 1-A2C 2-SAC 3-SALMUT 4-generate_N_lambd
    parser.add_argument("--algo", default=0, type=int)
    parser.add_argument("--baseline-threshold", default=18, type=int)
    parser.add_argument("--env_name", default="res_try_env")
    parser.add_argument("--logdir", default="res_try_log")
    parser.add_argument("--lambd", default=0.5, type=float)
    parser.add_argument("--lambd_high", default=0.75, type=float)
    parser.add_argument("--lambd_evolve", default=False,
                        type=lambda x: (str(x).lower() == 'true'))
    parser.add_argument("--user_identical", default=True,
                        type=lambda x: (str(x).lower() == 'true'))
    parser.add_argument("--user_evolve", default=False,
                        type=lambda x: (str(x).lower() == 'true'))
    parser.add_argument("--folder", default='res_try_0')
    parser.add_argument("--train_iter", default=1e6, type=int)
    parser.add_argument("--eval_freq", default=1e3, type=int)
    parser.add_argument("--offload_cost", default=1.0, type=float)
    parser.add_argument("--overload_cost", default=10.0, type=float)
    parser.add_argument("--holding_cost", default=0.12, type=float)
    parser.add_argument("--reward", default=0.2, type=float)
    parser.add_argument("--replay_buffer", default='replay_buffer')
    parser.add_argument("--N", default=24, type=int)
    parser.add_argument("--fc", default=0, type=int)
    parser.add_argument("--run", default=1, type=int)
    args = parser.parse_args()

    print("---------------------------------------")
    if args.train_behavioral:
        print(
            f"Setting: Training behavioral, Env: {args.env}, Seed: {args.seed}")
    elif args.generate_buffer:
        print(
            f"Setting: Generating buffer, Env: {args.env}, Seed: {args.seed}")
    else:
        print(f"Setting: Training BCQ, Env: {args.env}, Seed: {args.seed}")
    print("---------------------------------------")

    if args.train_behavioral and args.generate_buffer:
        print("Train_behavioral and generate_buffer cannot both be true.")
        exit()

    if not os.path.exists(args.folder):
        os.makedirs(args.folder)

    if not os.path.exists(f"./{args.folder}/results"):
        os.makedirs(f"./{args.folder}/results")

    if not os.path.exists(f"./{args.folder}/models"):
        os.makedirs(f"./{args.folder}/models")

    if not os.path.exists(f"./{args.folder}/buffers"):
        os.makedirs(f"./{args.folder}/buffers")

    if not os.path.exists(args.logdir):
        os.makedirs(args.logdir)
    print("Lambda Evolve ", args.lambd_evolve, " User Identical ",
          args.user_identical, " User evolve ", args.user_evolve)
    # Make env and determine properties
    # env, is_atari, state_dim, num_actions = utils.make_env(
    #    args.env, atari_preprocessing)
    is_atari = False
    #state_dim = 4
    state_dim = 2
    num_actions = 2
    #eval_env = OffloadEnv(True, args.lambd, args.mdp_evolve, args.user_evolve, args.user_identical, args.env_name)
    #env_name = "offload_dqn_mdp_5"
    env_name = args.env_name
    setting = f"{env_name}_{args.seed}"
    buffer_name = f"{args.buffer_name}_{args.run}"
    #env = DummyVecEnv([lambda: env])
    #log_dir = "./off_a2c_res_5/"
    log_dir = args.logdir
    #env = make_vec_env(lambda: env, n_envs=1)
    #eval_env = make_vec_env(lambda: eval_env, n_envs=1)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    #model = DQN.load('dqn-offload')
    #print (model)
    #callback = SaveOnBestTrainingRewardCallback(check_freq=10, log_dir=log_dir)
    loop_range = int(args.train_iter / args.eval_freq)
    replay_buffer = utils.ReplayBuffer(
        # state_dim, is_atari, atari_preprocessing, args.eval_freq, args.eval_freq, 'cpu')
        state_dim, is_atari, atari_preprocessing, 10000, 10000, 'cpu')
    replay_buffer.load(args.folder, args.replay_buffer)
    if args.algo == 3:
        model = structured_learning.structured_learning(
            False, num_actions, state_dim, device, args.BCQ_threshold)
        if int(args.fc) - 1 > 0:
            run = int(args.run)
            thres_vec = np.load(
                f"./{args.folder}/buffers/thresvec_{run}_{env_name}_{int(args.fc) - 1}.npy")
            val_fn = np.load(
                f"./{args.folder}/buffers/val_fn_{run}_{env_name}_{int(args.fc) - 1}.npy")
            state_counts = np.load(
                f"./{args.folder}/buffers/state_counts_{run}_{env_name}_{int(args.fc) - 1}.npy")
            #print("Threshold vector present ", thres_vec, int(args.fc) - 1)
            model.set_threshold_vec(thres_vec, val_fn, state_counts)
        model.train(replay_buffer, env_name, args.folder,
                    int(args.fc), int(args.run), args.eval_freq)
    exit(1)
    for j in range(0, 10):
        print("RANDOM SEED ", j)
        lambd = []
        N = []
        env = OffloadEnv(False, args.lambd, args.offload_cost,
                         args.overload_cost, args.holding_cost, args.reward, args.N, j, args)
        env = Monitor(env, log_dir)
        # env.seed(j)
        # torch.manual_seed(j)
        np.random.seed(j)
        if args.algo != 4:
            with open(f"./{args.folder}/buffers/lambda.npy", "rb") as fp:
                lambd = pickle.load(fp)
            with open(f"./{args.folder}/buffers/N.npy", "rb") as fp:
                N = pickle.load(fp)
        if args.algo == 0:
            model = PPO('MlpPolicy', env, verbose=0,
                        gamma=0.95, tensorboard_log=log_dir)
        elif args.algo == 1:
            model = A2C('MlpPolicy', env, verbose=0,
                        gamma=0.95, tensorboard_log=log_dir)
        elif args.algo == 2:
            model = SAC('MlpPolicy', env, verbose=0,
                        gamma=0.95, tensorboard_log=log_dir)
        elif args.algo == 3:
            model = structured_learning.structured_learning(
                False, num_actions, state_dim, device, args.BCQ_threshold)
        state = env.reset()
        for i in range(loop_range):
            print("TRAIN ", i)
            if args.algo == 4:
                if i > 0 and args.user_evolve == True and i % 100 == 0:
                    old_N = env.get_N()
                    new_N = old_N
                    new_lambd = env.get_lambd()
                    for ru in range(old_N):
                        z = np.random.binomial(n=1, p=0.1, size=1)[0]
                        if z == 1:
                            p = np.random.binomial(n=1, p=0.5, size=1)[0]
                            if p == 1:
                                new_N += 1
                                new_lambd.append(args.lambd)
                            else:
                                new_N -= 1
                                del new_lambd[-1]
                    env.set_N(new_N, new_lambd)
                    print("USER EVOLVE ", env.get_N(), env.get_lambd())
                if i > 0 and args.lambd_evolve == True and i % 10 == 0:
                    curr_N = env.get_N()
                    if args.user_identical == False:
                        new_lambd = []
                        for x in range(curr_N):
                            p = np.random.binomial(n=1, p=0.1, size=1)[0]
                            if p == 0:
                                new_lambd.append(args.lambd)
                            else:
                                new_lambd.append(args.lambd_high)
                        env.set_lambd(new_lambd)
                    else:
                        print(i, loop_range/3, loop_range/3 * 2)
                        if i > (loop_range/3) and i < (loop_range/3 * 2):
                            new_lambd = [args.lambd_high] * curr_N
                        else:
                            new_lambd = [args.lambd] * curr_N
                        env.set_lambd(new_lambd)
                    print("LAMBDA EVOLVE ", env.get_lambd())
                lambd.append(env.get_lambd())
                N.append(env.get_N())
                #print (env.get_lambd(), env.get_N())
                with open(f"./{args.folder}/buffers/lambda.npy", "wb") as fp:
                    pickle.dump(lambd, fp)
                with open(f"./{args.folder}/buffers/N.npy", "wb") as fp:
                    pickle.dump(N, fp)
                # model.learn(total_timesteps=5000, log_interval=10,
                #            callback=callback, reset_num_timesteps=False)
            else:
                env.set_N(int(N[i]), list(lambd[i]))
                #print ("Lambda, N", N[i], lambd[i])

            if args.algo != 3 and args.algo != 4:
                model.learn(total_timesteps=args.eval_freq, log_interval=10,
                            reset_num_timesteps=False)
                model_name = f"./{args.folder}/models/model_{args.algo}_{j}_{i}"
                model.save(model_name)
            # np.save(f"./{args.folder}/buffers/lambda_{args.algo}_{j}.npy", lambd)
            # np.save(f"./{args.folder}/buffers/N_{args.algo}_{j}.npy", N)
            if args.algo == 0:
                model = PPO.load(model_name, env)
            elif args.algo == 1:
                model = A2C.load(model_name, env)
            elif args.algo == 2:
                model = SAC.load(model_name, env)
            elif args.algo == 3:
                state = train_salmut(
                    env, model, args.eval_freq, args, state, j)
        #parameters = atari_parameters if is_atari else regular_parameters
        if args.algo == 4:
            exit(1)
        end_time = time.time() - start_time
        start_time = time.time()
        time_file = f'./{args.folder}/buffers/time_{args.algo}.txt'
        if os.path.exists(time_file):
            append_write = 'a'  # append if already exists
        else:
            append_write = 'w'  # make a new file if not
            f = open(time_file, append_write)
            f.write("Time : " + str(end_time) + '\n')
            f.close()

    #cpu_util = []
    #action_list = []
    print("END TIME ", end_time)
    """
    # Initialize buffer
    replay_buffer = utils.ReplayBuffer(
        state_dim, is_atari, atari_preprocessing, parameters["batch_size"], parameters["buffer_size"], device)

    if args.train_behavioral or args.generate_buffer:
        interact_with_environment(
            env, replay_buffer, is_atari, num_actions, state_dim, device, args, parameters)
    else:
        train_BCQ(env, replay_buffer, is_atari, num_actions,
                  state_dim, device, args, parameters)
    """
