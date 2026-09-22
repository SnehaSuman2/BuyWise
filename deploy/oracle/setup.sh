#!/usr/bin/env bash
# Prepare a fresh Oracle Cloud Ubuntu instance to run the BuyWise API.
#
# Run it on the instance, not on your laptop:
#   ssh ubuntu@<your-instance-ip>
#   curl -fsSL https://raw.githubusercontent.com/SnehaSuman2/BuyWise/main/deploy/oracle/setup.sh | bash
#
# It installs Docker, opens the firewall (Oracle blocks everything but SSH at
# two separate layers; this handles the one inside the machine), and clones the
# repository. It does not start anything: you still have to write the .env.

set -euo pipefail

REPO="${REPO:-https://github.com/SnehaSuman2/BuyWise.git}"
DIR="${DIR:-$HOME/BuyWise}"

say() { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }

say "Updating packages"
sudo apt-get update -qq
sudo apt-get install -y -qq ca-certificates curl git ufw

if ! command -v docker >/dev/null; then
  say "Installing Docker"
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg |
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" |
    sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER"
else
  say "Docker already installed"
fi

# Oracle's Ubuntu images ship iptables rules that drop everything except SSH.
# This is the step people miss: the cloud Security List can be wide open and the
# machine still refuses connections because of these local rules.
say "Opening ports 80 and 443 inside the machine"
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save >/dev/null 2>&1 || sudo apt-get install -y -qq iptables-persistent

if [ -d "$DIR/.git" ]; then
  say "Updating the existing clone at $DIR"
  git -C "$DIR" pull --ff-only
else
  say "Cloning into $DIR"
  git clone --depth 1 "$REPO" "$DIR"
fi

say "Done"
cat <<'NEXT'

Still to do, on this machine:

  1. Write the environment file:
         nano ~/BuyWise/.env
     Copy every value from the Render dashboard, and add one line Render does
     not have:
         API_DOMAIN=api.buywise.co.in
     API_PUBLIC_URL must be https://<that same domain>.

  2. Point the domain at this machine: an A record for api.buywise.co.in to
     this instance's public IP. Caddy cannot get a certificate until it resolves.

  3. Check the cloud firewall too, in the Oracle console:
     Networking > Virtual Cloud Networks > your VCN > Security Lists > default,
     add ingress rules for TCP 80 and TCP 443 from 0.0.0.0/0.

  4. Start it:
         cd ~/BuyWise
         docker compose -f deploy/oracle/docker-compose.yml up -d --build

     If docker says permission denied, log out and back in first: the group
     change from this script needs a new session.

  5. Watch the first boot, which includes getting a certificate:
         docker compose -f deploy/oracle/docker-compose.yml logs -f

NEXT
