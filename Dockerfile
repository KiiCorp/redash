FROM redash/base:latest

# We first copy only the requirements file, to avoid rebuilding on every file
# change.
COPY requirements.txt requirements_dev.txt requirements_all_ds.txt ./
RUN pip install -r requirements.txt -r requirements_dev.txt -r requirements_all_ds.txt

# Install python modules for VFE.
RUN pip install pandas
RUN pip install numpy

COPY . ./
RUN npm install && npm run build && rm -rf node_modules
RUN chown -R redash /app
USER redash

COPY redash-setup.sh redash-setup.py ./

ENTRYPOINT ["/app/bin/docker-entrypoint"]
