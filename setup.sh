#!/usr/bin/bash -ex

# install firefox without snap
# Reference: https://www.omgubuntu.co.uk/2022/04/how-to-install-firefox-deb-apt-ubuntu-22-04

sudo install -d -m 0755 /etc/apt/keyrings

wget -q https://packages.mozilla.org/apt/repo-signing-key.gpg -O- | sudo tee /etc/apt/keyrings/packages.mozilla.org.asc > /dev/null

echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" | sudo tee -a /etc/apt/sources.list.d/mozilla.list > /dev/null

echo '
Package: *
Pin: origin packages.mozilla.org
Pin-Priority: 1000

Package: firefox*
Pin: release o=Ubuntu
Pin-Priority: -1' | sudo tee /etc/apt/preferences.d/mozilla
sudo apt update

sudo apt install -y firefox

# download geckodriver
which geckodriver >/dev/null 2>/dev/null
if [[ $? -eq 0 ]]; then
    echo "geckodriver already installed"
else
    wget "https://github.com/mozilla/geckodriver/releases/download/v0.36.0/geckodriver-v0.36.0-linux64.tar.gz" \
        -O /tmp/geckodriver.tar.gz
    sudo tar -xzf /tmp/geckodriver.tar.gz -C /usr/local/bin
    rm -f /tmp/geckodriver.tar.gz
fi

# install pdftotext
which pdftotext >/dev/null 2>/dev/null
if [[ $? -eq 0 ]]; then
    echo "pdftotext already installed"
else
    sudo apt install -y poppler-utils
fi

if [[ -f $PWD/requirements.txt ]]; then
    pip install -r $PWD/requirements.txt
fi

exit 0
