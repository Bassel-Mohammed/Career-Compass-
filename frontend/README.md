# CareerCompass Frontend

This directory is reserved for the browser UI. The recommended starting point
is a React + TypeScript application using Vite.

The frontend should call the Spring Boot API at `http://localhost:8080` and
must not call the internal FastAPI service directly. Spring Security already
allows the Vite development origin `http://localhost:5173`.
