
ARG BUILD_FROM
FROM ${BUILD_FROM}

# Cài python + pip + tini (base của HA không có sẵn Python)
RUN apk add --no-cache python3 py3-pip tini

# Cài Python deps
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/requirements.txt

# App
COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

EXPOSE 8099
ENTRYPOINT ["/sbin/tini","-g","--"]
CMD [ "/run.sh" ]