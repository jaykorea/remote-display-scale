#!/usr/bin/env bash
set -e

APP_DIR="$HOME/.local/share/cocelo-display-scale"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"

mkdir -p "$APP_DIR/assets" "$DESKTOP_DIR"

cp "$SOURCE_DIR/display_scale_app.py" "$APP_DIR/display_scale_app.py"
cp "$SOURCE_DIR/assets/cocelo-display-scale.png" "$APP_DIR/assets/cocelo-display-scale.png"
chmod +x "$APP_DIR/display_scale_app.py"

cat > "$APP_DIR/launch.sh" <<'EOF'
#!/usr/bin/env bash
APP="$HOME/.local/share/cocelo-display-scale/display_scale_app.py"
LOG="$HOME/.local/share/cocelo-display-scale/app.log"
for C in "$HOME/anaconda3/etc/profile.d/conda.sh" "$HOME/miniconda3/etc/profile.d/conda.sh" "$HOME/mambaforge/etc/profile.d/conda.sh" "$HOME/miniforge3/etc/profile.d/conda.sh"; do
    if [ -f "$C" ]; then
        source "$C"
        conda activate base
        exec python "$APP" >> "$LOG" 2>&1
    fi
done
if [ -x /usr/bin/python3 ]; then
    exec /usr/bin/python3 "$APP" >> "$LOG" 2>&1
else
    exec python3 "$APP" >> "$LOG" 2>&1
fi
EOF
chmod +x "$APP_DIR/launch.sh"

cat > "$DESKTOP_DIR/Cocelo_Display_Scale.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Cocelo Display Scale
Comment=Set logical display resolution for RustDesk
Exec=/bin/bash -lc "exec ~/.local/share/cocelo-display-scale/launch.sh"
Terminal=false
Categories=Utility;
StartupNotify=true
EOF
printf 'Icon=%s\n' "$APP_DIR/assets/cocelo-display-scale.png" >> "$DESKTOP_DIR/Cocelo_Display_Scale.desktop"

chmod +x "$DESKTOP_DIR/Cocelo_Display_Scale.desktop"
gio set "$DESKTOP_DIR/Cocelo_Display_Scale.desktop" metadata::trusted true 2>/dev/null || true

echo "Installed desktop launcher:"
echo "$DESKTOP_DIR/Cocelo_Display_Scale.desktop"
echo
echo "If Ubuntu blocks it, right-click the icon and select 'Allow Launching'."
