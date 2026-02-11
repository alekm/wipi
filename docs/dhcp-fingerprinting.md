# DHCP Fingerprinting

WiPi supports DHCP fingerprinting to make Raspberry Pis appear as different device types to network equipment. This is useful for testing how network infrastructure (like Ruckus One, MDU 360) classifies and handles different device types.

## How It Works

DHCP fingerprinting works by customizing:

1. **Hostname**: Device-specific naming patterns (e.g., `DESKTOP-XXXX` for Windows, `iPhone-XXXX` for iOS)
2. **Vendor Class Identifier** (DHCP Option 60): Identifies the device manufacturer/OS
3. **Parameter Request List** (DHCP Option 55): The order and list of DHCP options requested

These three elements combined create a unique "fingerprint" that network equipment uses to identify device types.

## Available Profiles

WiPi includes 20+ pre-configured device profiles:

### Desktop/Laptop Computers
- **windows10** / **windows11**: Windows 10/11 desktop or laptop
  - Hostname: `DESKTOP-XXXX`
  - Vendor: `MSFT 5.0`

- **macos**: macOS (MacBook/iMac)
  - Hostname: `MacBook-Pro-XXXX`
  - No vendor class (typical for macOS)

- **macbook**: MacBook laptop
  - Hostname: `MacBook-XXXX`

- **linux**: Generic Linux desktop
  - Hostname: `ubuntu-XXXX`
  - Vendor: `dhcpcd-9.4.1`

### Mobile Devices
- **iphone**: Apple iPhone
  - Hostname: `iPhone-XXXX`
  - Vendor: `AAPLBM` (Apple Bonjour)

- **ipad**: Apple iPad
  - Hostname: `iPad-XXXX`
  - Vendor: `AAPLBM`

- **android**: Generic Android device
  - Hostname: `android-XXXX`
  - Vendor: `android-dhcp-11`

- **samsung**: Samsung Galaxy phone/tablet
  - Hostname: `Galaxy-XXXX`
  - Vendor: `android-dhcp-13`

- **pixel**: Google Pixel phone
  - Hostname: `Pixel-XXXX`
  - Vendor: `android-dhcp-13`

### Gaming Consoles
- **xbox**: Xbox One/Series
  - Hostname: `XboxOne-XXXX`
  - Vendor: `MSFT 5.0`

- **playstation**: PlayStation 5
  - Hostname: `PlayStation-XXXX`

### Smart Home / IoT
- **echo**: Amazon Echo smart speaker
  - Hostname: `Echo-XXXX`
  - Vendor: `dhcpcd-6.8.2:Linux-3.18.22-WeTek-4.9+`

- **echo-dot**: Amazon Echo Dot
  - Hostname: `Echo-Dot-XXXX`

### Streaming Devices
- **smart-tv-samsung**: Samsung Smart TV
  - Hostname: `Samsung-TV-XXXX`
  - Vendor: `Samsung`

- **smart-tv-lg**: LG Smart TV
  - Hostname: `LG-webOS-XXXX`
  - Vendor: `LG`

- **chromecast**: Google Chromecast
  - Hostname: `Chromecast-XXXX`

- **roku**: Roku streaming stick
  - Hostname: `Roku-XXXX`

## Using DHCP Personalities in Scenarios

### Manual Scenario (JSON)

Add the `dhcp_personality` field to any interface configuration:

```json
{
  "name": "Test Scenario",
  "pis": [
    {
      "pi_id": "wipi-01",
      "interfaces": [
        {
          "name": "wlan0_1",
          "ssid": "MyNetwork",
          "password": "MyPassword",
          "dhcp_personality": "windows10",
          "traffic": {...}
        },
        {
          "name": "wlan0_2",
          "ssid": "MyNetwork",
          "password": "MyPassword2",
          "dhcp_personality": "iphone",
          "traffic": {...}
        }
      ]
    }
  ]
}
```

### Resident Simulation

When using resident simulation, you can specify `dhcp_personality` in the interface configuration. If not specified, the system will generate a random realistic hostname (but won't use full fingerprinting).

**Future Enhancement**: The resident simulator could intelligently assign personalities based on traffic patterns:
- Video streaming → Smart TV, Chromecast, Roku
- Gaming traffic → Xbox, PlayStation
- Browsing → Windows, macOS, mobile devices
- IoT patterns → Echo, smart home devices

## Verifying DHCP Fingerprinting

### Check Generated Config Files

On a Pi, check the generated dhclient.conf:

```bash
sudo cat /tmp/dhclient_wlan0_1.conf
```

Example for Windows 10:
```
# DHCP fingerprint profile: Windows 10/11 Desktop
# Windows 10/11 desktop or laptop

send host-name "DESKTOP-9577";
send vendor-class-identifier "MSFT 5.0";

request subnet-mask,
        domain-name,
        routers,
        domain-name-servers,
        netbios-name-servers,
        ...
```

### Check Agent Logs

```bash
sudo journalctl -u wipi-agent | grep -i "dhcp\|personality"
```

Look for lines like:
```
Starting DHCP for wlan0_1 as windows10
Using DHCP profile 'windows10' for wlan0_1 as DESKTOP-9577
```

### Check Network Equipment

In Ruckus One or MDU 360:
1. Navigate to client list
2. Find the client by MAC address or IP
3. Check the "Device Type" or "Operating System" field
4. It should show the fingerprinted device type (Windows, iPhone, Xbox, etc.)

## Technical Details

### DHCP Options

The system uses dhclient configuration files to customize DHCP behavior:

- **Option 12**: Hostname
- **Option 55**: Parameter Request List (order matters!)
- **Option 60**: Vendor Class Identifier

Different devices request different DHCP options in different orders. Network equipment uses these patterns to classify devices.

### Hostname Generation

Each profile includes a hostname pattern with `{random}` placeholder:
- `DESKTOP-{random}` → `DESKTOP-9577`
- `iPhone-{random}` → `iPhone-3421`
- `XboxOne-{random}` → `XboxOne-7829`

Random suffixes are 4 digits for most devices, 3 digits for some (like MacBook).

### Implementation

DHCP fingerprinting is implemented in:
- `/opt/stacks/wipi/agent/src/core/dhcp_profiles.py` - Profile definitions
- `/opt/stacks/wipi/agent/src/core/dhcp_manager.py` - dhclient config generation
- `/opt/stacks/wipi/agent/src/api/apply.py` - Integration with apply flow

## Limitations

1. **Fingerprinting only works with dhclient**: The udhcpc client has limited customization options
2. **Detection depends on network equipment**: Not all systems use DHCP fingerprinting for device classification
3. **MAC address OUI still visible**: The MAC address vendor prefix (OUI) may still indicate Raspberry Pi hardware. Consider MAC randomization for full stealth.

## Testing

A test scenario is available at `/opt/stacks/wipi/test-fingerprint-scenario.json` that demonstrates:
- Windows 10 (wipi-01, wlan0_1)
- iPhone (wipi-01, wlan0_2)
- Xbox (wipi-02, wlan0_1)
- Amazon Echo (wipi-02, wlan0_2)
- MacBook (wipi-03, wlan0_1)
- Samsung Galaxy (wipi-03, wlan0_2)

Apply it with:
```bash
curl -X POST http://localhost:8000/api/scenarios \
  -H "Content-Type: application/json" \
  -d @test-fingerprint-scenario.json

curl -X POST http://localhost:8000/api/scenarios/{scenario_id}/apply
```
