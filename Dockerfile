FROM redash/base:latest

# Controls whether to install extra dependencies needed for all data sources.
ARG skip_ds_deps

# We first copy only the requirements file, to avoid rebuilding on every file
# change.
COPY requirements.txt requirements_dev.txt requirements_all_ds.txt ./
RUN pip install -r requirements.txt -r requirements_dev.txt
RUN if [ "x$skip_ds_deps" = "x" ] ; then pip install -r requirements_all_ds.txt ; else echo "Skipping pip install -r requirements_all_ds.txt" ; fi

# Install python modules for VFE.
COPY requirements_kii.txt ./
RUN pip install -r requirements_kii.txt

COPY . ./
RUN npm install && npm run bundle && npm run build && rm -rf node_modules
RUN chown -R redash /app
USER redash

COPY redash-setup.sh redash-setup.py ./

ENTRYPOINT ["/app/bin/docker-entrypoint"]
CMD ["server"]