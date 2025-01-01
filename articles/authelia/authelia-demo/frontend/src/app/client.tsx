'use client'

import React from "react";
import axios from "axios";

export default function ClientComponent() {
    const callApi = async () => {
    const apiUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:5000/api';
    const username = process.env.NEXT_PUBLIC_API_USERNAME || 'default-username';
    const password = process.env.NEXT_PUBLIC_API_PASSWORD || 'default-password';

    try {
      const response = await axios.get(apiUrl, {
        auth: {
            username: username,
            password: password
          },
      });
      console.log(response.data);
      alert('API called successfully!');
    } catch (error) {
      console.error('Error:', error);
      alert('API call failed.');
    }
  };

  return (
    <button onClick={callApi} className="rounded-full border border-solid border-transparent transition-colors flex items-center justify-center bg-foreground text-background gap-2 hover:bg-[#383838] dark:hover:bg-[#ccc] text-sm sm:text-base h-10 sm:h-12 px-4 sm:px-5">
      Call backend API
    </button>
  );
};

