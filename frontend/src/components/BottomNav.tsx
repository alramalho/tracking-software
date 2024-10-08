"use client";

import React from "react";
import { Eye, Home, Pencil, User } from "lucide-react";
import { useNotifications } from "@/hooks/useNotifications";
import { useSession } from "@clerk/clerk-react";
import Link from "next/link";

const BottomNav = () => {
  const { notificationCount } = useNotifications();
  const { isSignedIn } = useSession();

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white shadow-lg border-t-2 z-[1000]">
      <div className="flex justify-around">
        <Link
          href="/see"
          className="flex flex-col items-center p-2 text-gray-600 hover:text-blue-500 relative"
        >
          {notificationCount > 0 && (
            <div className="absolute top-0 right-0 bg-red-500 rounded-full w-5 h-5 flex items-center justify-center text-white text-xs">
              {notificationCount}
            </div>
          )}
          <Eye size={24} />
          <span className="text-xs mt-1">See</span>
        </Link>
        <Link
          href="/log"
          className="flex flex-col items-center p-2 text-gray-600 hover:text-blue-500"
        >
          <Pencil size={24} />
          <span className="text-xs mt-1">Log</span>
        </Link>
        {isSignedIn && (
          <Link
            href="/profile"
            className="flex flex-col items-center p-2 text-gray-600 hover:text-blue-500"
          >
            <User size={24} />
            <span className="text-xs mt-1">Profile</span>
          </Link>
        )}
      </div>
    </nav>
  );
};

export default BottomNav;
