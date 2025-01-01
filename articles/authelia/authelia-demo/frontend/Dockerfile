FROM node:22-alpine

WORKDIR /app
COPY package.json package-lock.json ./

ENV NEXT_PUBLIC_BACKEND_API_URL https://backend.example.com:8000
ENV NEXT_PUBLIC_API_USERNAME authelia
ENV NEXT_PUBLIC_API_PASSWORD authelia

RUN npm install
COPY . .
RUN npm run build


CMD ["npm", "start"]
