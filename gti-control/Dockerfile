ARG BUILD_FROM
FROM ${BUILD_FROM}

# Python + pip + virtualenv + tini
RUN apk add --no-cache python3 py3-pip py3-virtualenv tini

# VENV để tránh PEP 668
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Python deps
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# App
WORKDIR /app
COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

EXPOSE 8099
ENTRYPOINT ["/sbin/tini","-g","--"]
CMD ["/run.sh"]
