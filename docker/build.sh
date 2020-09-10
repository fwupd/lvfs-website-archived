#!/usr/bin/env bash
set -e

# $commit should be the short hash of the commit to release
commit=$1

if [ -d "lvfs-website" ]
then
    rm -rf lvfs-website
fi

git clone https://gitlab.com/linuxfoundation/lvfs-website
cd lvfs-website
git checkout "$commit"
cd ..

tag="linuxfoundation/lvfs-website:$commit"
dated_tag="${tag}-$(date -I)"
docker build -t "$tag" --build-arg commit="$commit" .
docker tag "$tag" "$dated_tag"
