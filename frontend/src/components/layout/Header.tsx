"use client";

import React, { useEffect, useState } from "react";
import { useTheme } from "@/lib/theme";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Search, Bell, Bot, Menu, X, Moon, Sun, Sparkles, LayoutDashboard, LogOut, Crown, User as UserIcon } from "lucide-react";
import { useAuth } from "@/lib/auth";

export default function Header() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [dark, toggleDark] = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  const links = [
    { href: "/", label: "Search", icon: Search },
    { href: "/agent", label: "AI Agent", icon: Bot },
    { href: "/alerts", label: "Alerts", icon: Bell },
    { href: "/pricing", label: "Pro", icon: Crown },
  ];

  const handleLogout = async () => { setMenuOpen(false); await logout(); router.push("/"); };

  return (
    <header className="sticky top-0 z-50 glass-strong">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link href="/" className="flex items-center gap-2 group" aria-label="BuyWise home">
            <div className="w-8 h-8 rounded-lg gradient-primary flex items-center justify-center"><Sparkles className="w-5 h-5 text-white" /></div>
            <span className="text-xl font-bold bg-gradient-to-r from-indigo-500 to-purple-500 bg-clip-text text-transparent">BuyWise</span>
          </Link>

          <nav className="hidden md:flex items-center gap-1" aria-label="Main">
            {links.map((link) => {
              const Icon = link.icon;
              const active = pathname === link.href;
              return (
                <Link key={link.href} href={link.href} className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${active ? "bg-indigo-500/10 text-indigo-500" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`}>
                  <Icon className="w-4 h-4" />{link.label}
                </Link>
              );
            })}
          </nav>

          <div className="flex items-center gap-2">
            <button onClick={toggleDark} className="p-2 rounded-lg hover:bg-muted transition-colors" aria-label="Toggle dark mode">{dark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}</button>
            {user ? (
              <div className="relative hidden md:block">
                <button onClick={() => setMenuOpen(!menuOpen)} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium hover:bg-muted transition-colors" aria-haspopup="menu" aria-expanded={menuOpen}>
                  <span className="w-7 h-7 rounded-full bg-indigo-500/15 text-indigo-500 flex items-center justify-center text-xs font-bold">{(user.display_name || user.username).slice(0, 2).toUpperCase()}</span>
                  <span className="max-w-[120px] truncate">{user.display_name || user.username}</span>
                  {user.plan === "pro" && <Crown className="w-4 h-4 text-amber-500" />}
                </button>
                {menuOpen && (
                  <div className="absolute right-0 mt-2 w-52 glass-strong rounded-xl p-1 shadow-xl animate-slide-down" role="menu">
                    <Link href="/dashboard" onClick={() => setMenuOpen(false)} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm hover:bg-muted" role="menuitem"><LayoutDashboard className="w-4 h-4" /> Dashboard</Link>
                    <Link href="/account" onClick={() => setMenuOpen(false)} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm hover:bg-muted" role="menuitem"><UserIcon className="w-4 h-4" /> Account</Link>
                    <button onClick={handleLogout} className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm hover:bg-muted text-left" role="menuitem"><LogOut className="w-4 h-4" /> Sign out</button>
                  </div>
                )}
              </div>
            ) : (
              <Link href="/login" className="hidden md:inline-flex px-4 py-2 rounded-lg text-sm font-medium bg-indigo-500 text-white hover:bg-indigo-600 transition-colors">Sign in</Link>
            )}
            <button onClick={() => setMobileOpen(!mobileOpen)} className="md:hidden p-2 rounded-lg hover:bg-muted transition-colors" aria-label="Menu" aria-expanded={mobileOpen}>{mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}</button>
          </div>
        </div>

        {mobileOpen && (
          <nav className="md:hidden pb-4 animate-slide-down" aria-label="Mobile">
            {links.map((link) => { const Icon = link.icon; return (
              <Link key={link.href} href={link.href} onClick={() => setMobileOpen(false)} className="flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"><Icon className="w-4 h-4" />{link.label}</Link>
            ); })}
            {user ? (
              <>
                <Link href="/dashboard" onClick={() => setMobileOpen(false)} className="flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted"><LayoutDashboard className="w-4 h-4" />Dashboard</Link>
                <Link href="/account" onClick={() => setMobileOpen(false)} className="flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted"><UserIcon className="w-4 h-4" />Account</Link>
                <button onClick={() => { setMobileOpen(false); handleLogout(); }} className="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium text-rose-500 text-left"><LogOut className="w-4 h-4" />Sign out</button>
              </>
            ) : (
              <Link href="/login" onClick={() => setMobileOpen(false)} className="flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium text-indigo-500">Sign in</Link>
            )}
          </nav>
        )}
      </div>
    </header>
  );
}
