


bump: # v2
	bumpversion patch
	git push --tags
	git push

package=duckietown-docker-utils-daffy

upload: # v3
	aido-check-not-dirty
	aido-check-tagged
	aido-check-need-upload --package $(package) make upload-do

upload-do:
	rm -f dist/*
	rm -rf src/*.egg-info
	python setup.py sdist
	twine upload --skip-existing --verbose dist/*


bump-upload:
	$(MAKE) bump
	$(MAKE) upload

