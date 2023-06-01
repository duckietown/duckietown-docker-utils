


bump: # v2
	bumpversion patch
	git push --tags
	git push


upload:
	rm -f dist/*
	rm -rf src/*.egg-info
	python3 setup.py sdist
	twine upload --skip-existing --verbose dist/*


bump-upload:
	$(MAKE) bump
	$(MAKE) upload
