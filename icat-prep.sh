# This script re-orgs the OrgBook repo in preparation for merge into indy-catalyst
#
# Before running this script:
# - create a new branch (e.g. merge_test) so a to not screw up master
#
# Run this script from TheOrgBook root
#
# After running this script:
# - commit into github (into the new branch)
#
# In the indy-catalyst repo:
# - start on a new branch (for safety)
# - git remote add orgbook https://github.com/bcgov/TheOrgBook.git
# - git fetch orgbook
# - git merge orgbook/merge-test (or whatever you called your branch)
#
# To build the starter kit (server):
# - cd to credential-registry/server
# - ./icat-prep.sh # builds packages for tob-api
# - cd to starter-kits/credential-registry/server/docker
# - update manage script (see README files in the above credential-registry/server sub-directories)
# - ./manage build
# - ./manage start
#
# Note it requires a von network to be already running

mkdir starter-kits
mkdir starter-kits/credential-registry
mkdir starter-kits/credential-registry/client
mkdir starter-kits/credential-registry/server

rm .gitignore
rm .gitattributes

shopt -s extglob
mv !(starter-kits|icat-prep.sh) starter-kits/credential-registry/server/

mkdir credential-registry
mkdir credential-registry/client
mkdir credential-registry/server
mkdir credential-registry/server/django-icat-api
mkdir credential-registry/server/python-indy-api

mv starter-kits/credential-registry/server/tob-api/api_v2 credential-registry/server/django-icat-api/
mv starter-kits/credential-registry/server/tob-api/api_indy credential-registry/server/python-indy-api/
# TODO figure out where the tob-web code needs to live
#mv starter-kits/credential-registry/server/tob-web starter-kits/credential-registry/client/

rm starter-kits/credential-registry/server/Deploy*
rm starter-kits/credential-registry/server/SonarQube-*
rm starter-kits/credential-registry/server/Zap-*
rm -rf starter-kits/credential-registry/server/openshift
rm -rf starter-kits/credential-registry/server/sonar-runner
rm -rf starter-kits/credential-registry/server/tob-backup
