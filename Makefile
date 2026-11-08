.RECIPEPREFIX := >
SUBSET ?= 0
CONFIG ?= training/config.yaml
IMAGE := kd-train:v1

.PHONY: train train-image

train-image:
> docker build -t $(IMAGE) training

train: train-image
> docker run --rm -e SUBSET=$(SUBSET) -e HF_HOME=/work/.hf_cache -v "$(CURDIR):/work" -w /work $(IMAGE) python training/train.py --config $(CONFIG)

.PHONY: service-image
service-image:
> docker build -t kd-service:v1 service

.PHONY: up down
up:
> python scripts/make_up.py

down:
> k3d cluster delete cloudlab
