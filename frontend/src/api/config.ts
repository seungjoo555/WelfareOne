import type { ServerConfig } from "../types/contract";
import { request } from "./client";

export const getServerConfig = () => request<ServerConfig>("/config");
