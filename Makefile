

# Add remote url for mainstream
add-remote-url:
	git remote add base https://github.com/arnydo/Synapse
# Update from mainstream
update-from-origin:
	git fetch base
	git merge base/master
# Build the docker container
docker-build:
	docker build -t synapse -f Dockerfile .
# DEV only
update-toc:
	docker run -v $(shell pwd)":/app" -w /app --rm -it sebdah/markdown-toc README.md --skip-headers 1 --replace --inline
