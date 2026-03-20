SHELL := /bin/bash
COMPOSE := docker compose
SERVICE := control-plane

.PHONY: help build up down restart logs ps config pull clean

help:
	@echo "make build    - build control-plane image"
	@echo "make up       - start control-plane"
	@echo "make down     - stop control-plane"
	@echo "make restart  - restart control-plane"
	@echo "make logs     - follow control-plane logs"
	@echo "make ps       - show compose status"
	@echo "make config   - render compose config"
	@echo "make pull     - pull base images"
	@echo "make clean    - stop and remove local containers"

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart $(SERVICE)

logs:
	$(COMPOSE) logs -f $(SERVICE)

ps:
	$(COMPOSE) ps

config:
	$(COMPOSE) config

pull:
	$(COMPOSE) pull

clean:
	$(COMPOSE) down --remove-orphans
