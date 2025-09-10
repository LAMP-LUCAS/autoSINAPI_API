# Começa com a imagem oficial do Kong
FROM kong:3.4

# Mude temporariamente para o usuário root para ter permissão de instalar pacotes
USER root

# Usa o apt-get (para Debian) em vez do apk (para Alpine)
# 1. Atualiza a lista de pacotes disponíveis
# 2. Instala o cliente do postgresql sem pedir confirmação (-y)
# 3. Limpa o cache para manter a imagem pequena
RUN apt-get update \
    && apt-get install -y postgresql-client \
    && rm -rf /var/lib/apt/lists/*


# IMPORTANTE: Retorna para o usuário padrão 'kong' por segurança
USER kong