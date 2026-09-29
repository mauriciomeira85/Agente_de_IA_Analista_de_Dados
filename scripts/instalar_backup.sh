#!/bin/bash
# INTRODUÇÃO
# Instala timer systemd próprio (a VM não possui cron), sem editar outros jobs.
set -euo pipefail
RAIZ="$(cd -- "$(dirname -- "$0")/.." && pwd)"
USUARIO="$(id -un)"
mkdir -p "$HOME/backups/agente_analista_dados"
chmod 700 "$HOME/backups/agente_analista_dados"
chmod +x "$RAIZ/scripts/backup.sh"
sudo tee /etc/systemd/system/agente-analista-dados-backup.service >/dev/null <<EOF
[Unit]
Description=Backup do banco Agente Analista de Dados
[Service]
Type=oneshot
User=$USUARIO
Environment=HOME=$HOME
ExecStart=/bin/bash $RAIZ/scripts/backup.sh
EOF
sudo tee /etc/systemd/system/agente-analista-dados-backup.timer >/dev/null <<'EOF'
[Unit]
Description=Backup diario Agente Analista de Dados
[Timer]
OnCalendar=*-*-* 03:17:00 America/Sao_Paulo
Persistent=true
[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now agente-analista-dados-backup.timer
sudo systemctl start agente-analista-dados-backup.service
systemctl list-timers agente-analista-dados-backup.timer --no-pager
# RESUMO: backup diário às 03:17 de São Paulo, com recuperação de execução perdida.
