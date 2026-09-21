# IceWarp LDAP test lab

Ansible wrapper that optionally creates an Infralab EL9 VM, installs **389 Directory Server** natively or in Docker, loads an IceWarp-oriented directory tree, and optionally points an existing IceWarp server at it for one-way LDAP→IceWarp user/group sync and LDAP bind authentication.

389-ds is used in both install modes so the suffix, bind DN, and IceWarp `syncad.dat` fragment stay the same. IceWarp expects generic LDAP operational attributes `entryUUID` and `modifyTimestamp` (both provided by 389-ds). EL9 does not ship `openldap-servers`.

## Layout

| Path | Role |
|------|------|
| `deploy.sh` | Staged deploy (`provision` → `docker` → `ldap` → `ldap_data` → `icewarp` → `smoke`) |
| `prepare_ansible_host.sh` | Control-node venv (`~/ansible-venv`, ansible-core 2.19) |
| `inventory/infralab/` | Default site: hypervisor, LDAP host, optional IceWarp host |
| `roles/kvmvps` | Slim single-NIC Infralab KVM clone (mgmt / `vcl2-mon` only) |
| `roles/docker` | Docker CE on EL9 (skipped if the engine is already up, or `SKIP_DOCKER=1`) |
| `roles/ldap_389ds` | Native `dscreate` or `quay.io/389ds/dirsrv` with host ports 389/636 |
| `roles/ldap_icewarp_data` | Fixture domain, users, groups, `uid=iwsync` bind account |
| `roles/icewarp_ldap_sync` | Merge IceWarp `syncad.dat` + ADSync logging (existing IceWarp only) |
| `roles/ldap_smoke` | Localhost `ldapsearch` of domain, users, groups |
| `roles/icewarp_smoke` | Wait for ADSync finished log, `tool.sh export`, IMAP + WebClient login |

## Prerequisites

- Ansible control node: Linux EL9 or macOS, Python 3.11
- Infralab KVM (optional): SSH as root to `HYPERVISOR_IP`, template `tpl_L1_OB_almalinux9.qcow2` under `/kvmstore/templates/`
- Prepared-host mode: reachable EL9 (or Docker) LDAP server in `ldap_hosts`
- IceWarp stage: existing IceWarp install with `/opt/icewarp/tool.sh`

## Control node

```bash
./prepare_ansible_host.sh
source ~/ansible-venv/bin/activate
```

## Secrets

```bash
cp group_vars/all/vault.yml.example group_vars/all/vault.yml
# edit Directory Manager / bind / fixture user passwords
echo 'your-vault-password' > ~/.vault_password.txt
ansible-vault encrypt group_vars/all/vault.yml
```

`deploy.sh` passes `--vault-password-file=../.vault-pass` when that file exists; otherwise Ansible uses `vault_password_file` from `ansible.cfg` (`~/.vault_password.txt`). `vault.yml` is gitignored. For an unencrypted lab copy, skip `ansible-vault encrypt`.

Ansible only auto-loads `group_vars` next to the playbook (`playbooks/group_vars`) and next to the inventory. `playbooks/group_vars` is a symlink to repo-root `group_vars/`, so `group_vars/all/vault.yml` and `group_vars/all/main.yml` are actually in the play’s variable path.

## Inventory

Edit [`inventory/infralab/hosts.yml`](inventory/infralab/hosts.yml):

1. **LDAP VM IP/MAC** — allocate a mgmt reservation on the hypervisor, then set `ansible_host`, `VM_IF_MGMT_IP`, and `VM_IF_MGMT_MAC`:

   ```bash
   ssh root@185.138.220.201 /root/generate_dnsmasq_reservation.sh vcl2-mon
   ```

2. **IceWarp** — add hosts under `icewarp_hosts`, or leave `hosts: {}` to skip that stage automatically.

Site vars live in [`inventory/infralab/group_vars/all.yml`](inventory/infralab/group_vars/all.yml) (`ldap_mail_domain`, hypervisor, `IFNAME_MGMT`).

`PLATFORM=kvm` always **destroys and recreates** the libvirt domain `{{ HYPERVISOR_VM_PREFIX }}_{{ VM_NAME }}`.

## Usage

```bash
# New Infralab EL9 VM + native 389-ds + IceWarp (if icewarp_hosts is filled)
SITE=infralab PLATFORM=kvm LDAP_MODE=native ./deploy.sh

# Cross-domain: LDAP ldaptest.loc users created as *@iwldaptest.loc in IceWarp
IW_SYNC_MODE=crossdomain IW_SYNC_DOMAIN=iwldaptest.loc SITE=infralab ./deploy.sh

# Prepared EL9, LDAP in Docker, no IceWarp
SKIP_PROVISION=1 SKIP_ICEWARP=1 LDAP_MODE=docker SITE=infralab ./deploy.sh

# Existing Docker host, DIT only
SKIP_PROVISION=1 SKIP_DOCKER=1 SKIP_ICEWARP=1 LDAP_MODE=docker SITE=infralab ./deploy.sh

# Resume unfinished stages
RESUME=1 SITE=infralab ./deploy.sh

# Clear deploy state and run all stages again
RESET_DEPLOY_STATE=1 SITE=infralab ./deploy.sh

# Smoke tests only (LDAP listing + IceWarp sync wait / IMAP / WebClient)
SKIP_PROVISION=1 SKIP_DOCKER=1 SKIP_LDAP=1 SKIP_LDAP_DATA=1 SKIP_ICEWARP=1 SITE=infralab ./deploy.sh
```

### Environment flags

| Variable | Effect |
|----------|--------|
| `SITE` | Inventory directory under `inventory/` (default `infralab`) |
| `PLATFORM` | `linux` (prepared hosts, default) or `kvm` (create VM) |
| `LDAP_MODE` | `native` (EL9 389-ds packages) or `docker` (`quay.io/389ds/dirsrv`) |
| `SKIP_PROVISION` | Skip KVM / prepared-host provision play |
| `SKIP_DOCKER` | Skip Docker CE (required on non-EL9 if you already have an engine) |
| `SKIP_LDAP` | Skip 389-ds install |
| `SKIP_LDAP_DATA` | Skip DIT / fixture users |
| `SKIP_ICEWARP` | Skip IceWarp `syncad.dat` merge |
| `SKIP_SMOKE` | Skip LDAP + IceWarp localhost smoke tests |
| `IW_SYNC_MODE` | `onetoone` (default) or `crossdomain` |
| `IW_SYNC_DOMAIN` | IceWarp target domain (default: `ldap_mail_domain`; required to differ in `crossdomain`) |
| `RESUME` | Skip stages listed in `inventory/<SITE>/.deploy-state` |
| `RESET_DEPLOY_STATE` | Delete `.deploy-state` before running |
| `VAULT_PASS` | Vault password file (default `../.vault-pass`) |

Docker CE is still installed on new EL9 VMs when LDAP is native (lab host with Docker available). Native 389-ds does not use the engine.

Containerized 389-ds listens on **3389/3636** inside the container; the role publishes **389:3389** and **636:3636** so IceWarp always uses standard ports.

## Directory tree

Default mail domain `ldaptest.loc` → suffix `dc=ldaptest,dc=loc`:

```text
dc=ldaptest,dc=loc
  ou=people
    uid=alice, bob, carol, dave   inetOrgPerson + mail (synced to IceWarp)
    uid=nomail                    inetOrgPerson without mail (excluded by IceWarp filter)
  ou=groups
    cn=sales                      alice, bob
    cn=engineering                carol, dave
  ou=services
    uid=iwsync                    IceWarp bind account (read ACI + operational attrs)
```

Fixture user password is `LDAP_USER_PASSWORD`. Bind password is `LDAP_BIND_PASSWORD`.

## IceWarp sync and auth

When `icewarp_hosts` is non-empty, the last stage:

- Creates IceWarp domain `icewarp_sync_domain` if missing (`tool.sh create domain`). Default is `ldap_mail_domain` (1:1).
- Merges one `<DOMAIN>` node into `syncad.dat` keyed by that IceWarp domain (other domains are kept). Switching 1:1 vs cross-domain does not delete the other domain’s block. Config dir is `/opt/icewarp/config` unless `/opt/icewarp/path.dat` exists with a non-empty path on line 1, in which case that path is used (trailing slashes stripped). Do not inspect `/opt/icewarp/config/syncad.dat` when `path.dat` points elsewhere.

Set `icewarp_sync_mode` / `icewarp_sync_domain` in **site** `inventory/<site>/group_vars/` (or `IW_SYNC_MODE` / `IW_SYNC_DOMAIN`). Role defaults are 1:1; those keys are not in repo-root `group_vars/all/main.yml` because playbook-dir group_vars would override the inventory.
- Sets `c_system_adsynclogtype=3` and keeps vCard sync enabled
- Restarts IceWarp control (falls back to `--restart all`)

Two sync modes (`icewarp_sync_mode` / `IW_SYNC_MODE`):

**1:1** (`onetoone`, default): IceWarp domain equals the LDAP mail domain. `HOSTDOMAINACTIVE=0`, empty `HOSTDOMAIN`. Example: LDAP `mail=*@ldaptest.loc` → IceWarp `*@ldaptest.loc`.

**Cross-domain** (`crossdomain`): IceWarp domain is `icewarp_sync_domain` / `IW_SYNC_DOMAIN`; LDAP filter still matches `mail=*@ldap_mail_domain*`; `HOSTDOMAINACTIVE=1` and `HOSTDOMAIN` is `{ldap_directory_domain};{ldap_mail_domain}` (both default to `ldap_mail_domain`) so IceWarp rewrites the directory domain and the LDAP `mail` domain. Example: `<HOSTDOMAIN>ldaptest.loc;ldaptest.loc</HOSTDOMAIN>` → IceWarp `iwldaptest.loc`. A single token without the semicolon makes IceWarp skip users whose `mail` domain differs from the IceWarp domain.

ACCOUNTFILTERS always search the LDAP source domain. The `&` in the LDAP filter is XML-escaped as `&amp;` in `syncad.dat`.

Sync is **LDAP → IceWarp only**:

- Accounts: `(&(objectClass=inetOrgPerson)(mail=*@<domain>*))`
- Groups: `(objectClass=groupOfNames)`
- Identity: `GUIDSOURCE=entryUUID`
- Change detection: `WHENCHANGEDSOURCE=modifyTimestamp` (IceWarp compares to `adsyncrec.dat` and refreshes the local vCard/versit when LDAP data changed)
- `LDAPVCARDWINS=1` so LDAP wins over IceWarp-side card edits
- `LDAPUSERFROMDN=1` so `u_authmodevalue` is `host;uid=...,ou=people,...`

IceWarp sets **`u_authmode=2`** (LDAP / Active Directory) on synced accounts. Logins bind IceWarp → 389-ds with PLAIN. IceWarp polls about every five minutes (`c_accounts_global_activedirectorysyncinterval`). ADSync logs: `/opt/icewarp/logs/adsync/`.

Default LDAP URL is `ldap://<ldap_host>:389`. Set `ldap_use_ldaps: true` in group vars to use `ldaps://<ldap_host>:636` (instance self-signed cert).

`ldap_server_type` (IceWarp `LDAPSERVERTYPE`) defaults to **1** (Generic LDAP). Override if a given IceWarp build expects `0`.

## Smoke tests

The `smoke` stage (after IceWarp) lists directory data and checks that synced accounts can authenticate. Re-run it alone with `SKIP_PROVISION=1 SKIP_DOCKER=1 SKIP_LDAP=1 SKIP_LDAP_DATA=1 SKIP_ICEWARP=1`, or `ansible-playbook -i inventory/<site> playbooks/smoke.yml`. `SKIP_SMOKE=1` disables it.

On the LDAP host (`127.0.0.1`): bind as `uid=iwsync` and list the suffix, people, and groups. Expected mail users are alice/bob/carol/dave; expected groups are sales/engineering. `nomail` may appear in LDAP and is not required in IceWarp.

On each IceWarp host:

1. Sets `c_system_adsynclogtype=3`
2. Reads the node-id prefix from line 4 of `/opt/icewarp/path.dat` (log name e.g. `/opt/icewarp/logs/adsync/303120260921-00.log`)
3. Restarts IceWarp control and waits (up to ~15 minutes) for a **new** `Synchronizing domain <icewarp_sync_domain> finished` line
4. `tool.sh export domain` and `tool.sh export account user@domain` for expected users (`u_type=0`, `u_authmode=2`) and groups (`u_type=7`)
5. IMAP LOGIN as `{uid}@{icewarp_sync_domain}` with `LDAP_USER_PASSWORD` (not admin impersonation)
6. WebClient login with that same user password: `getauthtoken` on `https://127.0.0.1/icewarpapi/`, then `/webmail/?atoken=` and `webmail.php` session auth

Ansible prints the listings. A Markdown report is always written on the control node under `reports/smoke-<site>-<timestamp>.md`; the play and `deploy.sh` print that path when finished.

## Out of scope

- Samba/AD, OpenLDAP, FreeIPA, multi-master 389-ds
- IceWarp→LDAP export, SSO/Kerberos
- Installing IceWarp itself
- Automatic IP/MAC allocation (use the hypervisor reservation script)
