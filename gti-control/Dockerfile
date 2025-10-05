ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip py3-virtualenv tini

# tạo venv riêng
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

EXPOSE 8099
ENTRYPOINT ["/sbin/tini","-g","--"]
CMD [ "/run.sh" ]