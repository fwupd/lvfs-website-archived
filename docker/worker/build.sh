#!/usr/bin/env bash
set -e

# $commit should be the short hash from the commit to release
commit=$1

rm -rf lvfs-website
git clone https://github.com/fwupd/lvfs-website
cd lvfs-website
git checkout "$commit"
cd ..

tag="dwtalton/lvfs-celery-worker:$commit"
dated_tag="${tag}-$(date -I)"

docker build -t "$tag" --build-arg commit="$commit" .
docker tag "$tag" "$dated_tag"

# push here
#docker login -u "$DOCKER_USERNAME"
#docker push "$tag"
#docker push "$dated_tag"
