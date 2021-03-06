import sys, os
import signal
import os
import json

import numpy as np
import torch
from six.moves import shlex_quote

from config import argparser
from rl.trainers.off_policy_trainer import OffPolicyTrainer
from rl.trainers.on_policy_trainer import OnPolicyTrainer
from util.logger import logger


np.set_printoptions(precision=3)
np.set_printoptions(suppress=True)

def run(config):
    make_log_files(config)

    def shutdown(signal, frame):
        logger.warning('Received signal %s: exiting', signal)
        sys.exit(128+signal)

    signal.signal(signal.SIGHUP, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # set global seed
    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    torch.cuda.manual_seed_all(config.seed)

    os.environ["DISPLAY"] = ":1"

    if config.gpu is not None:
        os.environ["CUDA_VISIBLE_DEVICES"] = "{}".format(config.gpu)
        assert torch.cuda.is_available()
        config.device = torch.device("cuda")
    else:
        config.device = torch.device("cpu")

    # build a trainer
    if config.algo == 'ppo':
        trainer = OnPolicyTrainer(config)
    else:
        trainer = OffPolicyTrainer(config)
    if config.is_train:
        trainer.train()
        logger.info("Finish training")
    else:
        if config.ll_type == 'mix' and config.subgoal_predictor:
            trainer.mp_evaluate()
            logger.info('Finish evaluating')
        else:
            trainer.evaluate()
            logger.info("Finish evaluating")

def make_log_files(config):
    config.run_name = 'rl.{}.{}.{}'.format(config.env, config.prefix, config.seed)

    config.log_dir = os.path.join(config.log_root_dir, config.run_name)
    logger.info('Create log directory: %s', config.log_dir)
    os.makedirs(config.log_dir, exist_ok=True)

    if config.is_train:
        config.record_dir = os.path.join(config.log_dir, 'video')
    else:
        config.record_dir = os.path.join(config.log_dir, 'eval_video')
    logger.info('Create video directory: %s', config.record_dir)
    os.makedirs(config.record_dir, exist_ok=True)

    if config.is_train:
        # log git diff
        cmds = [
            "echo `git rev-parse HEAD` >> {}/git.txt".format(config.log_dir),
            "git diff >> {}/git.txt".format(config.log_dir),
            "echo 'python -m rl.main {}' >> {}/cmd.sh".format(
                ' '.join([shlex_quote(arg) for arg in sys.argv[1:]]),
                config.log_dir),
        ]
        os.system("\n".join(cmds))

        # log config
        param_path = os.path.join(config.log_dir, 'params.json')
        logger.info('Store parameters in %s', param_path)
        with open(param_path, 'w') as fp:
            json.dump(config.__dict__, fp, indent=4, sort_keys=True)


if __name__ == '__main__':
    parser = argparser()
    args, unparsed = parser.parse_known_args()

    if len(unparsed):
        logger.error("Unparsed argument is detected:\n%s", unparsed)
    else:
        if args.debug:
            args.init_steps = 100
        run(args)
