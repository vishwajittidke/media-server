import React from 'react';

export const TermsOfService: React.FC = () => {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white p-8 md:p-16">
      <div className="max-w-3xl mx-auto backdrop-blur-md bg-white/5 p-8 rounded-2xl border border-white/10 shadow-2xl">
        <h1 className="text-4xl font-light mb-8 bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
          Terms of Service
        </h1>
        <div className="space-y-6 text-gray-300 font-light leading-relaxed">
          <p>
            By using Photo Server, you agree to these terms. If you do not agree, please do not use the service.
          </p>

          <h2 className="text-2xl font-medium text-white mt-8 mb-4">1. Acceptable Use</h2>
          <p>
            You are solely responsible for the content you upload and connect to Photo Server. You agree not to use the service to host, display, or transmit any material that is illegal, infringes on intellectual property rights, or constitutes Child Sexual Abuse Material (CSAM).
          </p>

          <h2 className="text-2xl font-medium text-white mt-8 mb-4">2. Zero Liability for Cloud Costs</h2>
          <p>
            Because Photo Server acts as a proxy to your personal cloud storage buckets (AWS, Supabase, Google Drive, etc.), you acknowledge that you are entirely responsible for any egress, bandwidth, or storage fees incurred by your cloud provider. Photo Server is not liable for misconfigured buckets or unexpected cloud bills.
          </p>

          <h2 className="text-2xl font-medium text-white mt-8 mb-4">3. DMCA & Copyright</h2>
          <p>
            We respect intellectual property rights. If you believe your copyrighted work is being hosted via our proxy illegally, please submit a DMCA notice. However, because we do not host the physical files, we may only be able to terminate the offending user's account and block the proxy route, rather than deleting the source files.
          </p>

          <h2 className="text-2xl font-medium text-white mt-8 mb-4">4. Account Termination</h2>
          <p>
            We reserve the right to terminate or suspend access to our service immediately, without prior notice or liability, for any reason whatsoever, including without limitation if you breach the Terms.
          </p>
        </div>
      </div>
    </div>
  );
};
