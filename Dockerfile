FROM node:10 as frontend-builder

WORKDIR /frontend
COPY package.json package-lock.json /frontend/
RUN npm install

COPY . /frontend
RUN npm run build

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

COPY . /app
COPY --from=frontend-builder /frontend/client/dist /app/client/dist
>>>>>>> 096140c0978eabee2d3b6a1ddfd870493c02e43c
RUN chown -R redash /app
USER redash

COPY redash-setup.sh redash-setup.py ./

ENTRYPOINT ["/app/bin/docker-entrypoint"]
CMD ["server"]
