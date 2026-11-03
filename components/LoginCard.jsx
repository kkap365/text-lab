"use client";
import { useState } from "react";
const API = process.env.NEXT_PUBLIC_API_BASE_URL;

export default function LoginCard({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isRegister, setIsRegister] = useState(false);

  async function handleSubmit() {
    setError("");
    const url = isRegister ? "/api/register" : "/api/login";
    try {
      const res = await fetch(`${API}${url}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (data.error) {
        setError(data.error);
        return;
      }
      // 登录成功：把 token 和用户名交给父组件
      onLogin(data.token, username);
    } catch (e) {
      setError("请求失败，请确认后端已启动");
    }
  }

  return (
    <article className="panel panel-full card">
      <div className="panel-heading">
        <p className="section-kicker">账户</p>
        <h3>{isRegister ? "注册" : "登录"}</h3>
      </div>
      <div className="lab-form">
        <label>用户名</label>
        <input value={username} onChange={(e) => setUsername(e.target.value)} />
        <label>密码</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="lab-error">{error}</p>}
        <button className="primary-button" type="button" onClick={handleSubmit}>
          {isRegister ? "注册" : "登录"}
        </button>
        <button type="button" onClick={() => setIsRegister(!isRegister)}>
          {isRegister ? "已有账号？去登录" : "没有账号？去注册"}
        </button>
      </div>
    </article>
  );
}