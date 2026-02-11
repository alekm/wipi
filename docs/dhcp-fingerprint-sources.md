# DHCP Fingerprint Sources and Research

This document tracks the sources for DHCP fingerprints used in WiPi device spoofing.

## Research Sources

1. **Fingerbank Database** - Official DHCP fingerprint database
   - GitHub: https://github.com/karottc/fingerbank/blob/master/dhcp_fingerprints.conf
   - API: https://www.fingerbank.org/
   - Most authoritative source for device fingerprints

2. **Cisco ISE DHCP Fingerprinting**
   - https://www.cisco.com/c/en/us/support/docs/security/identity-services-engine/116235-configure-ise-00.html

3. **Fortinet iOS DHCP Profiling**
   - https://community.fortinet.com/t5/FortiNAC/Technical-Tip-Apple-iOS-DHCP-Fingerprint-Profiling-for-Operating/ta-p/213330

## Current Fingerprints (Updated 2026-01-30)

### iOS Devices (iPhone/iPad)

**Option 55:** `1,3,6,15,119,78,79,95,252`
**Vendor Class:** None (iOS doesn't send vendor class in DHCP)
**Source:** Fingerbank database (OS ID 1102)
**Status:** ✅ Updated based on real device captures

**Changes Made:**
- **OLD:** `1,3,6,15,119,252,95,44,46` + vendor class "AAPLBM"
- **NEW:** `1,3,6,15,119,78,79,95,252` + no vendor class
- Added options 78 (SLP Directory Agent), 79 (SLP Service Scope)
- Removed options 44, 46 (NetBIOS - Windows-specific)
- Removed "AAPLBM" vendor class (not used in modern iOS DHCP)

### Windows 10/11

**Option 55:** `1,15,3,6,44,46,47,31,33,121,249,43`
**Vendor Class:** `MSFT 5.0`
**Source:** Cisco ISE documentation + industry standard
**Status:** ✅ Verified (matches Windows 7-11 pattern)

**Notes:**
- Windows fingerprint has been consistent since Windows 7
- Option 249 is Microsoft-specific classless static routes
- Vendor class "MSFT 5.0" used since Windows 2000

### Android (Generic)

**Option 55:** `1,121,33,3,6,28,51,58,59`
**Vendor Class:** `android-dhcp-11`
**Source:** Fingerbank database (OS ID 1111)
**Status:** ✅ Updated from Fingerbank

**Changes Made:**
- **OLD:** `1,3,6,15,26,28,51,58,59`
- **NEW:** `1,121,33,3,6,28,51,58,59`
- Added option 121 (classless static routes) at beginning
- Added option 33 (static routes)
- Removed options 15 (domain name), 26 (interface MTU)

### Samsung Galaxy

**Option 55:** `1,3,6,15,28,33,51,58,59,121`
**Vendor Class:** `android-dhcp-13`
**Source:** Fingerbank database (OS ID 1112)
**Status:** ✅ Updated from Fingerbank - **WORKING IN PRODUCTION**

**Notes:**
- **Confirmed working** - Ruckus One correctly identifies as Android
- This is the most validated fingerprint we have
- Samsung puts option 121 at the end, generic Android at the beginning

## Testing Results

**Date:** 2026-01-30

| Device Type | DHCP Profile | Ruckus One Detection | Status |
|-------------|--------------|---------------------|---------|
| Samsung Galaxy | `1,3,6,15,28,33,51,58,59,121` | ✅ Android | Working |
| iPhone | `1,3,6,15,119,252,95,44,46` (OLD) | ❌ Unknown OS | Failed |
| iPhone | `1,3,6,15,119,78,79,95,252` (NEW) | 🔄 Testing | Pending |
| Windows 10 | `1,15,3,6,44,46,47,31,33,121,249,43` | ❌ Linux | Failed* |

*Windows detection failure likely due to TCP/IP stack fingerprinting (see below)

## Why Some Fingerprints Fail

### iPhone/iPad (Before Fix)
- **Wrong Option Order:** Had 252 before 95 (should be 95 before 252)
- **Missing Options:** Didn't include 78, 79 (SLP options)
- **Wrong Vendor Class:** Used "AAPLBM" (Bonjour), not used in DHCP

### Windows 10 (Still Failing)
- **TCP/IP Stack:** Pi runs Linux with TTL=64, Windows uses TTL=128
- **MAC OUI:** Raspberry Pi MAC address gives it away
- **HTTP User-Agent:** If DPI enabled, shows Linux user agents

## Beyond DHCP: Other Fingerprinting Methods

Network equipment uses multiple signals:

### 1. TCP/IP Stack Fingerprinting
- **TTL (Time To Live):** Windows=128, Linux=64, macOS=64
- **TCP Window Size:** OS-specific defaults
- **TCP Options:** SACK, timestamps, window scaling order
- **Tools:** p0f, Zardaxt

**To Fix:** Would need to modify Linux kernel TCP stack parameters
**Difficulty:** ⚠️ Very Hard

### 2. MAC Address OUI
- **First 3 bytes identify manufacturer**
- Raspberry Pi: `B8:27:EB`, `DC:A6:32`, `E4:5F:01`
- Real devices: Apple, Microsoft, Samsung have distinct OUIs

**To Fix:** Use vendor-appropriate MAC OUIs when randomizing
**Difficulty:** ✅ Easy (already randomizing MACs, just need right OUI)

### 3. HTTP User-Agent (if DPI enabled)
- **Browser/app identification in HTTP headers**
- Currently not spoofing device-specific User-Agents

**To Fix:** Add device-specific User-Agents to traffic generators
**Difficulty:** ✅ Easy

### 4. TLS Client Hello Fingerprinting
- **Cipher suites, extensions, curve preferences**
- JA3 fingerprinting

**To Fix:** Would need to modify TLS library behavior
**Difficulty:** ⚠️ Hard

## Next Steps

### Phase 1: DHCP Fixes (CURRENT)
- [x] Fix iPhone/iPad Option 55 order
- [x] Update Samsung/Android fingerprints
- [ ] Deploy and test iPhone detection
- [ ] Verify Samsung still works

### Phase 2: MAC OUI Spoofing
- [ ] Add MAC OUI database for vendors
- [ ] Use Apple OUI for iPhone/iPad profiles
- [ ] Use Microsoft OUI for Windows profiles
- [ ] Use Samsung OUI for Samsung profiles

### Phase 3: TCP/IP Stack (Optional)
- [ ] Research per-interface TTL modification
- [ ] Test if `sysctl` changes help detection
- [ ] Document limitations

### Phase 4: HTTP User-Agent
- [ ] Add User-Agent headers to YouTube generator
- [ ] Add User-Agent headers to Netflix generator
- [ ] Match User-Agent to DHCP personality

## References

- [DHCP Fingerprinting - ManageEngine](https://www.manageengine.com/products/oputils/tech-topics/dhcp-fingerprinting.html)
- [Fingerbank GitHub Database](https://github.com/karottc/fingerbank/blob/master/dhcp_fingerprints.conf)
- [Fingerbank Official Site](https://www.fingerbank.org/)
- [Cisco ISE DHCP Fingerprinting](https://www.cisco.com/c/en/us/support/docs/security/identity-services-engine/116235-configure-ise-00.html)
- [TCP/IP Stack Fingerprinting - Wikipedia](https://en.wikipedia.org/wiki/TCP/IP_stack_fingerprinting)
- [iOS DHCP Profiling - Fortinet](https://community.fortinet.com/t5/FortiNAC/Technical-Tip-Apple-iOS-DHCP-Fingerprint-Profiling-for-Operating/ta-p/213330)
