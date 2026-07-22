import React from 'react';

export const PrivacyPolicy: React.FC = () => {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white p-8 md:p-16">
      <div className="max-w-3xl mx-auto backdrop-blur-md bg-white/5 p-8 rounded-2xl border border-white/10 shadow-2xl">
        <h1 className="text-4xl font-light mb-8 bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent">
          Privacy Policy
        </h1>
        <div className="space-y-6 text-gray-300 font-light leading-relaxed">
          <p>
            Welcome to Photo Server. We are committed to protecting your privacy and ensuring that your personal data is handled in a safe and responsible manner.
          </p>
          
          <h2 className="text-2xl font-medium text-white mt-8 mb-4">1. The "Bring Your Own Storage" Model</h2>
          <p>
            Unlike traditional cloud providers, Photo Server does not host your image files. Your files are uploaded directly to the cloud storage bucket you provide (e.g., AWS S3, Supabase, Google Drive). We only store metadata and encrypted access credentials in our database to facilitate the connection.
          </p>

          <h2 className="text-2xl font-medium text-white mt-8 mb-4">2. Data We Collect</h2>
          <ul className="list-disc pl-6 space-y-2">
            <li><strong>Account Information:</strong> Your email address and a securely hashed password.</li>
            <li><strong>Storage Credentials:</strong> API keys and connection strings, which are symmetrically encrypted at rest using AES-256.</li>
            <li><strong>Metadata:</strong> File names, sizes, EXIF data (if extracted), and locally cached thumbnails to improve performance.</li>
          </ul>

          <h2 className="text-2xl font-medium text-white mt-8 mb-4">3. Data Deletion (Right to be Forgotten)</h2>
          <p>
            You have the right to request the deletion of your account and all associated data. By deleting your account in the settings panel, we will permanently destroy your encrypted cloud credentials and all metadata/thumbnails from our PostgreSQL database. Note that deleting your Photo Server account will <strong>not</strong> delete the files residing in your personal cloud bucket, as we relinquish access upon account deletion.
          </p>
        </div>
      </div>
    </div>
  );
};
