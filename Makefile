


bump: # v2
	bumpversion patch
	git push --tags
	git push

package=duckietown-docker-utils-daffy

upload: # v3
	dt-check-not-dirty
	dt-check-tagged
	dt-check-need-upload --package $(package) make upload-do

upload-do:
	rm -f dist/*
	rm -rf src/*.egg-info
	python3 setup.py sdist
	twine upload --skip-existing --verbose dist/*


bump-upload:
	$(MAKE) bump
	$(MAKE) upload
