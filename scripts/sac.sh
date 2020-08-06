#!/bin/bash -x
gpu=$1
seed=$2
algo='sac'
prefix="SAC"
env="Reacher-v2"
# env="Hopper-v2"
debug="False"
log_root_dir="./logs"
entity="junyamada107"
project='rl-bank'
wandb='True'

python -m main \
    --log_root_dir $log_root_dir \
    --wandb True \
    --prefix $prefix \
    --env $env \
    --gpu $gpu \
    --debug $debug \
    --algo $algo \
    --seed $seed \
    --wandb $wandb \
    --entity $entity \
    --project $project
