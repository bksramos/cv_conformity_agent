# FILE: update_ollama_ip.sh
# Execute antes de rodar o projeto: bash update_ollama_ip.sh

WINDOWS_IP=$(ip route show | grep -i default | awk '{ print $3}')
sed -i "s|OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=http://$WINDOWS_IP:11434|" .env
echo "✅ OLLAMA_BASE_URL atualizado para http://$WINDOWS_IP:11434"