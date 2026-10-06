# bosch-thermostat-client-python

Python3 asyncio package to talk to Bosch Thermostats via their gateway.
Supported protocols are HTTP and XMPP.

Both are still in development.

## PoinTT API (Cloud-based Air Conditioning Control)

For Bosch air conditioning units accessed via the cloud PoinTT API:

### Setup

1. **Run OAuth setup script** to authenticate and obtain tokens:
   ```bash
   python3 examples/pointtapi_oauth_setup.py
   ```

2. **Use tokens in your application or Home Assistant**:
   - For standalone use: The script saves tokens to a file for automatic management
   - For Home Assistant: Use the tokens from the OAuth flow in your configuration

### Limitations

The PoinTT API has the following known limitations:

- **Single AC unit per device** - No multi-zone support
- **No scheduling capabilities** - Cannot configure time-based schedules
- **No preset configurations** - Cannot save or recall preset modes
- **Cloud-only control** - No local network control available
- **Limited properties** - Some properties (like detailed fan speed readings) may not be available from the API

### Home Assistant Integration

See the Home Assistant integration documentation for details on:
- Config entry setup with OAuth
- Token management and refresh
- Climate entity configuration

## Helper

Now there is extra command added with this package `bosch_cli`.

```shell
# Create Python virtual environment
$ python3 -m venv bosch-thermostat-client
$ source bosch-thermostat-client/bin/activate

# Install bosch-thermostat-client
$ pip install bosch-thermostat-client

# Use bosch_cli
$ bosch_cli --help
Usage: bosch_cli [OPTIONS] COMMAND [ARGS]...

  A tool to run commands against Bosch thermostat.

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  put    Send value to Bosch thermostat.
  query  Query values of Bosch thermostat.
  scan   Create rawscan of Bosch thermostat.

$ bosch_cli scan --help
Usage: bosch_cli scan [OPTIONS]

  Create rawscan of Bosch thermostat.

Options:
  --config PATH                   Read configuration from PATH.  [default:
                                  config.yml]
  --host TEXT                     IP address of gateway or SERIAL for XMPP
                                  [required]
  --token TEXT                    Token from sticker without dashes.
                                  [required]
  --password TEXT                 Password you set in mobile app.
  --protocol [XMPP|HTTP]          Bosch protocol. Either XMPP or HTTP.
                                  [required]
  --device [NEFIT|IVT|EASYCONTROL]
                                  Bosch device type. NEFIT, IVT or
                                  EASYCONTROL.  [required]
  -d, --debug                     Set Debug mode. Single debug is debug of
                                  this lib. Second d is debug of aioxmpp as
                                  well.
  -o, --output TEXT               Path to output file of scan. Default to
                                  [raw/small]scan_uuid.json
  --stdout                        Print scan to stdout
  -d, --debug
  -i, --ignore-unknown            Ignore unknown device type. Try to scan
                                  anyway. Useful for discovering new devices.
  -s, --smallscan [HC|DHW|SENSORS|RECORDINGS]
                                  Scan only single circuit of thermostat.
  --help                          Show this message and exit.
```
