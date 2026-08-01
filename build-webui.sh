#!/usr/bin/env bash
# Install npm deps and build the webui frontend
cd "$(dirname "$0")/webui" || exit 1
npm install && npm run build