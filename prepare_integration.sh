#!/bin/bash

# Замена const.py на обновленную версию
echo "Replacing const.py with updated version..."
cp custom_components/buspro/const_updated.py custom_components/buspro/const.py
rm custom_components/buspro/const_updated.py

# Создание архива
echo "Creating archive..."
mkdir -p dist
rm -f dist/hdl_buspro_integration.zip
zip -r dist/hdl_buspro_integration.zip custom_components/buspro

echo "Archive created at dist/hdl_buspro_integration.zip"
echo "Installation instructions:"
echo "1. Unzip the archive in your Home Assistant config directory"
echo "2. Restart Home Assistant"
echo "3. Add the HDL Buspro integration through the UI" 