package vn.httm.backend.service;

import lombok.RequiredArgsConstructor;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import vn.httm.backend.dto.auth.AuthResponse;
import vn.httm.backend.dto.auth.LoginRequest;
import vn.httm.backend.dto.auth.RegisterRequest;
import vn.httm.backend.entity.User;
import vn.httm.backend.repository.UserRepository;
import vn.httm.backend.security.JwtUtil;

@Service
@RequiredArgsConstructor
public class AuthService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtil jwtUtil;
    private final AuthenticationManager authenticationManager;

    public AuthResponse register(RegisterRequest request) {
        if (userRepository.existsByUsername(request.getUsername())) {
            throw new RuntimeException("Username đã tồn tại");
        }
        if (userRepository.existsByEmail(request.getEmail())) {
            throw new RuntimeException("Email đã được sử dụng");
        }

        User user = User.builder()
            .username(request.getUsername())
            .email(request.getEmail())
            .passwordHash(passwordEncoder.encode(request.getPassword()))
            .fullName(request.getFullName())
            .build();

        user = userRepository.save(user);
        String token = jwtUtil.generateToken(user.getUsername());

        return buildAuthResponse(token, user);
    }

    public AuthResponse login(LoginRequest request) {
        // Ném BadCredentialsException nếu sai thông tin
        authenticationManager.authenticate(
            new UsernamePasswordAuthenticationToken(request.getUsername(), request.getPassword())
        );

        User user = userRepository.findByUsername(request.getUsername())
            .orElseThrow(() -> new RuntimeException("Không tìm thấy user"));

        String token = jwtUtil.generateToken(user.getUsername());
        return buildAuthResponse(token, user);
    }

    private AuthResponse buildAuthResponse(String token, User user) {
        return AuthResponse.builder()
            .token(token)
            .tokenType("Bearer")
            .userId(user.getId())
            .username(user.getUsername())
            .email(user.getEmail())
            .fullName(user.getFullName())
            .build();
    }
}
