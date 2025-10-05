ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache tini

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

EXPOSE 8099
ENTRYPOINT ["/sbin/tini","-g","--"]
CMD [ "/run.sh" ]