ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python dependencies
RUN apk add --no-cache python3 py3-pip iproute2 vim can-utils
RUN pip3 install --break-system-packages python-can

WORKDIR /

COPY run.sh .
COPY gateway.py .
COPY tools/ /tools

RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
