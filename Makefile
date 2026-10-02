.DEFAULT_GOAL := cloud-help
.PHONY: cloud-help cloud-setup cloud-check
cloud-help:
	@echo 'Active PIKA project: g1-pika/. Run make cloud-setup, then make cloud-check.'
	@echo 'CPU/record-only development; no robot or GPU access.'
cloud-setup:
	$(MAKE) -C g1-pika cloud-setup
cloud-check:
	$(MAKE) -C g1-pika cloud-check
